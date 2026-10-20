package signature

import (
	"bytes"
	"context"
	"crypto"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ProtonMail/go-crypto/openpgp"
	"github.com/ProtonMail/go-crypto/openpgp/armor"
	"github.com/ProtonMail/go-crypto/openpgp/clearsign"
	"github.com/ProtonMail/go-crypto/openpgp/packet"
	"github.com/grafana/grafana/pkg/plugins"
	"github.com/grafana/grafana/pkg/plugins/config"
	"github.com/grafana/grafana/pkg/plugins/manager/pluginfakes"
)

//go:embed distribution-prometheus.txt
var distributionPrometheusFixture []byte

//go:embed distribution-tempo.txt
var distributionTempoFixture []byte

func TestDistributionProductionManifestReader(t *testing.T) {
	for _, body := range [][]byte{distributionPrometheusFixture, distributionTempoFixture} {
		calculator := provideDefaultTestService()
		manifest, err := calculator.readPluginManifest(context.Background(), body)
		if err != nil || manifest == nil || manifest.SignedByOrg != "ambicrafted" {
			t.Fatalf("approved production manifest rejected: %v", err)
		}
		modified := append(append([]byte(nil), body...), '\n')
		if _, err := calculator.readPluginManifest(context.Background(), modified); err == nil {
			t.Fatal("actual manifest reader accepted changed armored bytes")
		}
	}
}

type distributionDenyUnsigned struct{}

func (distributionDenyUnsigned) CanLoadPlugin(*plugins.Plugin) bool { return false }

// This integration test runs in the build with the actual assembled bundles.
// It exercises the upstream file inventory, identity/root-URL validation and
// final loader validator, not only the new cryptographic helper.
func TestDistributionRealBundleValidation(t *testing.T) {
	root := os.Getenv("GRAFANA_DISTRIBUTION_TEST_PLUGINS")
	if root == "" {
		t.Skip("set GRAFANA_DISTRIBUTION_TEST_PLUGINS to the assembled public bundles")
	}
	for _, identifier := range []string{"prometheus", "tempo"} {
		for _, mutation := range []string{"valid", "binary", "removed file", "extra file", "manifest", "version", "root URL"} {
			t.Run(identifier+"/"+mutation, func(t *testing.T) {
				folder := filepath.Join(root, identifier)
				if mutation != "valid" && mutation != "root URL" {
					destination := filepath.Join(t.TempDir(), "plugin")
					if err := os.CopyFS(destination, os.DirFS(folder)); err != nil {
						t.Fatal(err)
					}
					folder = destination
				}
				metadata, err := os.ReadFile(filepath.Join(folder, "plugin.json"))
				if err != nil {
					t.Fatal(err)
				}
				var data plugins.JSONData
				if err := json.Unmarshal(metadata, &data); err != nil {
					t.Fatal(err)
				}
				appURL := "http://localhost:3000/"
				switch mutation {
				case "binary":
					err = os.WriteFile(filepath.Join(folder, data.Executable+"_linux_amd64"), []byte("tampered executable"), 0644)
				case "removed file":
					err = os.Remove(filepath.Join(folder, "module.js"))
				case "extra file":
					err = os.WriteFile(filepath.Join(folder, "unsigned-extra.txt"), []byte("unapproved"), 0644)
				case "manifest":
					body, readErr := os.ReadFile(filepath.Join(folder, "MANIFEST.txt"))
					if readErr != nil {
						t.Fatal(readErr)
					}
					err = os.WriteFile(filepath.Join(folder, "MANIFEST.txt"), append(body, '\n'), 0644)
				case "version":
					data.Info.Version = "0.0.0-unapproved"
				case "root URL":
					appURL = "https://unapproved.example.invalid/"
				}
				if err != nil {
					t.Fatal(err)
				}
				calculator := provideTestServiceWithConfig(&config.PluginManagementCfg{GrafanaAppURL: appURL})
				signature, err := calculator.Calculate(context.Background(), &pluginfakes.FakePluginSource{}, plugins.FoundPlugin{
					JSONData: data, FS: mustNewStaticFSForTests(t, folder),
				})
				if err != nil {
					t.Fatal(err)
				}
				plugin := &plugins.Plugin{JSONData: data, Signature: signature.Status, Class: plugins.ClassExternal}
				err = NewValidator(distributionDenyUnsigned{}).ValidateSignature(plugin)
				if mutation == "valid" {
					if err != nil || !signature.Status.IsValid() || signature.Type != plugins.SignatureTypePrivate {
						t.Fatalf("approved bundle rejected: %+v / %v", signature, err)
					}
				} else if err == nil || signature.Status.IsValid() {
					t.Fatalf("forbidden bundle reached loader acceptance: %+v", signature)
				}
			})
		}
	}
}

func distributionTestKey(t *testing.T) (*openpgp.Entity, []byte) {
	t.Helper()
	key, err := openpgp.NewEntity("Synthetic distribution", "", "fixture@example.invalid", &packet.Config{RSABits: 2048})
	if err != nil {
		t.Fatal(err)
	}
	var output bytes.Buffer
	writer, err := armor.Encode(&output, openpgp.PublicKeyType, nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := key.Serialize(writer); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return key, output.Bytes()
}

func signDistributionTest(t *testing.T, key *openpgp.Entity, manifest PluginManifest) []byte {
	t.Helper()
	payload, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	var output bytes.Buffer
	writer, err := clearsign.Encode(&output, key.PrivateKey, &packet.Config{DefaultHash: crypto.SHA512})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := writer.Write(payload); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return output.Bytes()
}

func TestDistributionPinnedAuthority(t *testing.T) {
	key, public := distributionTestKey(t)
	foreign, foreignPublic := distributionTestKey(t)
	fingerprint := hex.EncodeToString(key.PrimaryKey.Fingerprint)
	keyID := fmt.Sprintf("%016x", key.PrimaryKey.KeyId)
	manifest := PluginManifest{
		Plugin: "tempo", Version: "13.2.4+synthetic", KeyID: keyID, Time: time.Now().Unix(),
		ManifestVersion: "2.0.0", SignatureType: plugins.SignatureTypePrivate,
		SignedByOrg: "ambicrafted", SignedByOrgName: "Ambicrafted local distribution",
		RootURLs: []string{"http://localhost:3000/"}, Files: map[string]string{"plugin.json": strings.Repeat("a", 64)},
	}
	body := signDistributionTest(t, key, manifest)
	digest := sha256.Sum256(body)
	permitted := map[string]distributionPlugin{"tempo": {manifest.Version, hex.EncodeToString(digest[:])}}
	check := func(data []byte, m PluginManifest, pub []byte, fp string, policy map[string]distributionPlugin) error {
		block, _ := clearsign.Decode(data)
		return verifyPinnedDistribution(data, m, block, pub, fp, keyID, policy)
	}
	if err := check(body, manifest, public, fingerprint, permitted); err != nil {
		t.Fatalf("authentic permitted manifest rejected: %v", err)
	}
	for name, alter := range map[string]func(*PluginManifest){
		"unapproved plugin":      func(m *PluginManifest) { m.Plugin = "mysql" },
		"different version":      func(m *PluginManifest) { m.Version = "13.2.5" },
		"foreign key id":         func(m *PluginManifest) { m.KeyID = "0000000000000000" },
		"forged official author": func(m *PluginManifest) { m.SignedByOrg = "grafana" },
		"forged official label":  func(m *PluginManifest) { m.SignedByOrgName = "Grafana Labs" },
		"nonprivate signature":   func(m *PluginManifest) { m.SignatureType = plugins.SignatureTypeGrafana },
		"missing root urls":      func(m *PluginManifest) { m.RootURLs = nil },
		"missing inventory":      func(m *PluginManifest) { m.Files = nil },
		"future manifest format": func(m *PluginManifest) { m.ManifestVersion = "2.1.0" },
	} {
		t.Run(name, func(t *testing.T) {
			changed := manifest
			alter(&changed)
			if err := check(body, changed, public, fingerprint, permitted); err == nil {
				t.Fatal("forbidden identity accepted")
			}
		})
	}
	t.Run("full manifest byte pin", func(t *testing.T) {
		modified := append(append([]byte(nil), body...), '\n')
		if err := check(modified, manifest, public, fingerprint, permitted); err == nil {
			t.Fatal("manifest byte change accepted despite unchanged signed plaintext")
		}
	})
	t.Run("foreign root", func(t *testing.T) {
		if err := check(body, manifest, foreignPublic, fingerprint, permitted); err == nil {
			t.Fatal("foreign public key accepted")
		}
	})
	t.Run("fingerprint mismatch", func(t *testing.T) {
		if err := check(body, manifest, public, strings.Repeat("0", 40), permitted); err == nil {
			t.Fatal("unapproved fingerprint accepted")
		}
	})
	t.Run("forged signature even with an approved byte digest", func(t *testing.T) {
		forged := signDistributionTest(t, foreign, manifest)
		hash := sha256.Sum256(forged)
		policy := map[string]distributionPlugin{"tempo": {manifest.Version, hex.EncodeToString(hash[:])}}
		if err := check(forged, manifest, public, fingerprint, policy); err == nil {
			t.Fatal("signature made by an untrusted key accepted")
		}
	})
	t.Run("unsigned input", func(t *testing.T) {
		if err := check([]byte("{}"), manifest, public, fingerprint, permitted); err == nil {
			t.Fatal("unsigned manifest accepted")
		}
	})
}
