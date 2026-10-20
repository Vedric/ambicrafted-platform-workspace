package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func roots(t *testing.T) ([]byte, []byte) {
	t.Helper()
	bad, err := os.ReadFile("distrusted-emsign-g3.crt")
	if err != nil {
		t.Fatal(err)
	}
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	// Same display name is deliberately insufficient grounds for distrust.
	cert := &x509.Certificate{SerialNumber: big.NewInt(2), Subject: pkix.Name{CommonName: "emSign ECC Root CA - G3"}, NotBefore: time.Unix(1, 0), NotAfter: time.Unix(2000000000, 0), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign}
	der, err := x509.CreateCertificate(rand.Reader, cert, cert, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	return bad, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
}

func write(t *testing.T, root, path string, data []byte) string {
	t.Helper()
	full := filepath.Join(root, path)
	if err := os.MkdirAll(filepath.Dir(full), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(full, data, 0644); err != nil {
		t.Fatal(err)
	}
	return full
}

func TestExactFingerprintAndUnrelatedBytes(t *testing.T) {
	bad, good := roots(t)
	input := append(append(append([]byte("# before\n"), good...), bad...), good...)
	out, keep, n, err := filter(input)
	if err != nil || n != 1 || len(keep) != 2 || !bytes.Equal(out, bytes.Replace(input, bytes.TrimSpace(bad), nil, 1)) {
		t.Fatalf("unexpected filter: %d %d %v", n, len(keep), err)
	}
}

func TestOpenSSLTrustedCertificateAux(t *testing.T) {
	bad, _ := roots(t)
	block, _ := pem.Decode(bad)
	aux, _ := asn1.Marshal([]int{1, 2})
	trusted := pem.EncodeToMemory(&pem.Block{Type: "TRUSTED CERTIFICATE", Bytes: append(block.Bytes, aux...)})
	_, keep, n, err := filter(trusted)
	if err != nil || n != 1 || len(keep) != 0 {
		t.Fatalf("trusted root not removed: %v", err)
	}
}

func TestBundleSourcesHashLinksAndPackageInventory(t *testing.T) {
	bad, good := roots(t)
	root := t.TempDir()
	bundle := append(append([]byte{}, good...), bad...)
	write(t, root, "etc/ssl/certs/ca-certificates.crt", bundle)
	source := write(t, root, "usr/share/ca-certificates/mozilla/bad.crt", bad)
	write(t, root, "etc/ca-certificates.conf", []byte("mozilla/bad.crt\nmozilla/good.crt\n"))
	inventory := write(t, root, "var/lib/dpkg/status", []byte("Package: ca-certificates\nVersion: original\n"))
	alias := filepath.Join(root, "etc/ssl/certs/bad.pem")
	if err := os.Symlink(source, alias); err != nil {
		t.Fatal(err)
	}
	hashLink := filepath.Join(root, "etc/ssl/certs/12345678.0")
	if err := os.Symlink("bad.pem", hashLink); err != nil {
		t.Fatal(err)
	}
	report, err := apply(root, "/etc/ssl/certs/ca-certificates.crt", false)
	if err != nil || report.Certificates != 2 || len(report.Links) != 2 || report.BundleRoots != 1 {
		t.Fatalf("%+v: %v", report, err)
	}
	for _, path := range []string{source, alias, hashLink} {
		if _, err = os.Lstat(path); !os.IsNotExist(err) {
			t.Fatalf("root/link survived %s", path)
		}
	}
	raw, _ := os.ReadFile(inventory)
	if string(raw) != "Package: ca-certificates\nVersion: original\n" {
		t.Fatal("inventory changed")
	}
	raw, _ = os.ReadFile(filepath.Join(root, "etc/ca-certificates.conf"))
	if !strings.HasPrefix(string(raw), "!mozilla/bad.crt\n") {
		t.Fatal("regeneration policy not disabled")
	}
	if _, err = apply(root, "/etc/ssl/certs/ca-certificates.crt", false); err == nil {
		t.Fatal("unexpected already-patched root accepted")
	}
	if _, err = apply(root, "/etc/ssl/certs/ca-certificates.crt", true); err != nil {
		t.Fatal(err)
	}
}

func TestRefuseEscapingTrustLink(t *testing.T) {
	bad, good := roots(t)
	root := t.TempDir()
	outside := t.TempDir()
	write(t, root, "etc/ssl/certs/ca-certificates.crt", good)
	file := write(t, outside, "bad.crt", bad)
	if err := os.Symlink(file, filepath.Join(root, "etc/ssl/certs/escape.pem")); err != nil {
		t.Fatal(err)
	}
	if _, err := apply(root, "/etc/ssl/certs/ca-certificates.crt", false); err == nil {
		t.Fatal("escaping link accepted")
	}
}

func TestRefuseEmptyEffectiveBundle(t *testing.T) {
	bad, _ := roots(t)
	root := t.TempDir()
	write(t, root, "etc/ssl/certs/ca-certificates.crt", bad)
	if _, err := apply(root, "/etc/ssl/certs/ca-certificates.crt", false); err == nil {
		t.Fatal("empty root store accepted")
	}
}

func TestRejectMalformedPEM(t *testing.T) {
	_, _, _, err := filter([]byte("-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----"))
	if err == nil {
		t.Fatal("malformed certificate silently accepted")
	}
}
