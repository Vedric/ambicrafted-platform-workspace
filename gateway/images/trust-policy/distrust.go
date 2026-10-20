// Build-only distrust of the exact emSign ECC G3 trust anchor.
// No package inventory, certificate verification setting or other root is removed.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/asn1"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
)

const distrusted = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"

var certificate = regexp.MustCompile(`(?s)-----BEGIN (?:TRUSTED )?CERTIFICATE-----.*?-----END (?:TRUSTED )?CERTIFICATE-----`)

func fingerprint(block []byte) (string, error) {
	decoded, rest := pem.Decode(block)
	if decoded == nil || len(bytes.TrimSpace(rest)) != 0 {
		return "", errors.New("invalid certificate PEM")
	}
	// OpenSSL TRUSTED CERTIFICATE appends X509_AUX to the ordinary DER certificate.
	var value asn1.RawValue
	remaining, err := asn1.Unmarshal(decoded.Bytes, &value)
	if err != nil || value.Tag != asn1.TagSequence || (decoded.Type == "CERTIFICATE" && len(remaining) != 0) {
		return "", errors.New("invalid certificate DER")
	}
	hash := sha256.Sum256(value.FullBytes)
	return hex.EncodeToString(hash[:]), nil
}

func filter(input []byte) ([]byte, []string, int, error) {
	var output []byte
	var preserved []string
	removed, cursor := 0, 0
	for _, location := range certificate.FindAllIndex(input, -1) {
		output = append(output, input[cursor:location[0]]...)
		block := input[location[0]:location[1]]
		hash, err := fingerprint(block)
		if err != nil {
			return nil, nil, 0, err
		}
		if hash == distrusted {
			removed++
		} else {
			preserved = append(preserved, hash)
			output = append(output, block...)
		}
		cursor = location[1]
	}
	output = append(output, input[cursor:]...)
	return output, preserved, removed, nil
}

type Report struct {
	Fingerprint  string   `json:"distrusted_sha256"`
	Changed      []string `json:"changed_files"`
	Deleted      []string `json:"deleted_single_certificate_files"`
	Links        []string `json:"removed_links"`
	Certificates int      `json:"removed_occurrences"`
	BundleRoots  int      `json:"remaining_bundle_roots"`
}

func apply(root, bundle string, allowPrepared bool) (Report, error) {
	report := Report{Fingerprint: distrusted}
	root, err := filepath.Abs(root)
	if err != nil {
		return report, err
	}
	paths := []string{"/etc/ssl/certs", "/etc/ssl/cert.pem", "/etc/pki/ca-trust/extracted", "/etc/pki/tls/certs", "/usr/share/ca-certificates", "/usr/local/share/ca-certificates"}
	files, aliases := map[string]bool{}, map[string]string{}
	contained := func(path string) bool {
		return root == "/" || path == root || strings.HasPrefix(path, root+string(os.PathSeparator))
	}
	for _, path := range paths {
		start := filepath.Join(root, path)
		resolved, resolveErr := filepath.EvalSymlinks(start)
		if errors.Is(resolveErr, fs.ErrNotExist) {
			continue
		}
		if resolveErr != nil {
			return report, resolveErr
		}
		if !contained(resolved) {
			return report, errors.New("trust directory escapes root")
		}
		if resolved != start {
			aliases[start] = resolved
		}
		err = filepath.WalkDir(resolved, func(path string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.Type()&os.ModeSymlink != 0 {
				target, linkErr := filepath.EvalSymlinks(path)
				if errors.Is(linkErr, fs.ErrNotExist) {
					return nil
				}
				if linkErr != nil {
					return linkErr
				}
				if !contained(target) {
					return errors.New("trust link escapes root")
				}
				aliases[path] = target
				info, statErr := os.Stat(target)
				if statErr != nil {
					return statErr
				}
				if info.Mode().IsRegular() {
					files[target] = true
				}
			} else if entry.Type().IsRegular() {
				files[path] = true
			}
			return nil
		})
		if err != nil {
			return report, err
		}
	}
	deleted := map[string]bool{}
	ordered := make([]string, 0, len(files))
	for path := range files {
		ordered = append(ordered, path)
	}
	slices.Sort(ordered)
	for _, path := range ordered {
		info, statErr := os.Stat(path)
		if statErr != nil {
			return report, statErr
		}
		if info.Size() > 16*1024*1024 {
			return report, errors.New("unexpected trust file size")
		}
		input, readErr := os.ReadFile(path)
		if readErr != nil {
			return report, readErr
		}
		output, preserved, removed, filterErr := filter(input)
		if filterErr != nil {
			return report, fmt.Errorf("%s: %w", path, filterErr)
		}
		if removed == 0 {
			continue
		}
		report.Certificates += removed
		relative, _ := filepath.Rel(root, path)
		if len(preserved) == 0 {
			if err = os.Remove(path); err != nil {
				return report, err
			}
			deleted[path] = true
			report.Deleted = append(report.Deleted, "/"+relative)
		} else {
			if err = os.WriteFile(path, output, info.Mode().Perm()); err != nil {
				return report, err
			}
			_, after, remains, verifyErr := filter(output)
			if verifyErr != nil || remains != 0 || !slices.Equal(after, preserved) {
				return report, errors.New("unrelated roots changed")
			}
			report.Changed = append(report.Changed, "/"+relative)
		}
	}
	for alias, target := range aliases {
		if deleted[target] {
			if err = os.Remove(alias); err != nil {
				return report, err
			}
			relative, _ := filepath.Rel(root, alias)
			report.Links = append(report.Links, "/"+relative)
		}
	}
	slices.Sort(report.Links)
	// Keep Debian's native regeneration policy from re-enabling the removed file.
	config := filepath.Join(root, "/etc/ca-certificates.conf")
	if raw, readErr := os.ReadFile(config); readErr == nil {
		lines := strings.Split(string(raw), "\n")
		for i, line := range lines {
			if deleted[filepath.Join(root, "/usr/share/ca-certificates", line)] {
				lines[i] = "!" + line
			}
		}
		if err = os.WriteFile(config, []byte(strings.Join(lines, "\n")), 0644); err != nil {
			return report, err
		}
	} else if !errors.Is(readErr, fs.ErrNotExist) {
		return report, readErr
	}
	input, err := os.ReadFile(filepath.Join(root, bundle))
	if err != nil {
		return report, err
	}
	_, roots, remains, err := filter(input)
	if err != nil || remains != 0 || len(roots) == 0 {
		return report, errors.New("effective CA bundle is invalid")
	}
	report.BundleRoots = len(roots)
	if report.Certificates == 0 && !allowPrepared {
		return report, errors.New("expected root not found; review upstream trust changes")
	}
	return report, nil
}

func main() {
	root := flag.String("root", "/", "Root of the image filesystem")
	bundle := flag.String("bundle", "/etc/ssl/certs/ca-certificates.crt", "Mandatory effective CA bundle")
	prepared := flag.Bool("native-prepared", false, "Native distrust was already applied and independently verified")
	reportPath := flag.String("report", "", "Optional public provenance report")
	flag.Parse()
	report, err := apply(*root, *bundle, *prepared)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if *reportPath != "" {
		data, marshalErr := json.MarshalIndent(report, "", "  ")
		if marshalErr != nil {
			fmt.Fprintln(os.Stderr, marshalErr)
			os.Exit(1)
		}
		if err = os.MkdirAll(filepath.Dir(*reportPath), 0755); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if err = os.WriteFile(*reportPath, append(data, '\n'), 0644); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
	if err = json.NewEncoder(os.Stdout).Encode(report); err != nil {
		os.Exit(1)
	}
}
