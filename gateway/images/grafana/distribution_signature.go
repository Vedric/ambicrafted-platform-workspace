package signature

import (
	"bytes"
	"crypto"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/ProtonMail/go-crypto/openpgp"
	"github.com/ProtonMail/go-crypto/openpgp/clearsign"
	"github.com/ProtonMail/go-crypto/openpgp/packet"
	"github.com/grafana/grafana/pkg/plugins"
)

// A private distribution authority is deliberately separate from Grafana Labs.
// The public key, complete manifest digests and identities are compiled in;
// neither environment variables, database records nor network retrieval can
// expand this authority. Every release requires a new reviewed core build.
const distributionKeyID = "f5fdd4382c05e115"
const distributionFingerprint = "9927b7037e53a8156725792ff5fdd4382c05e115"

//go:embed distribution-public.asc
var distributionPublicKey []byte

//go:embed distribution-manifests.json
var distributionManifestPolicy []byte

type distributionPlugin struct {
	Version string `json:"version"`
	SHA256  string `json:"sha256"`
}

func verifyDistributionManifest(body []byte, manifest PluginManifest, block *clearsign.Block) error {
	var permitted map[string]distributionPlugin
	if err := json.Unmarshal(distributionManifestPolicy, &permitted); err != nil {
		return fmt.Errorf("invalid compiled distribution policy: %w", err)
	}
	// This distribution implements only its two provisioned data sources.
	if len(permitted) != 2 || permitted["prometheus"].Version == "" || permitted["tempo"].Version == "" {
		return errors.New("distribution policy must contain exactly prometheus and tempo")
	}
	return verifyPinnedDistribution(body, manifest, block, distributionPublicKey,
		distributionFingerprint, distributionKeyID, permitted)
}

func verifyPinnedDistribution(body []byte, manifest PluginManifest, block *clearsign.Block,
	publicKey []byte, fingerprint, keyID string, permitted map[string]distributionPlugin) error {
	if block == nil {
		return errors.New("missing distribution signature")
	}
	if err := validateManifestFields(manifest); err != nil {
		return err
	}
	approved, exists := permitted[manifest.Plugin]
	if !exists || approved.Version != manifest.Version || manifest.KeyID != keyID ||
		manifest.ManifestVersion != "2.0.0" || manifest.SignatureType != plugins.SignatureTypePrivate ||
		manifest.SignedByOrg != "ambicrafted" || manifest.SignedByOrgName != "Ambicrafted local distribution" ||
		len(manifest.RootURLs) == 0 {
		return errors.New("distribution plugin identity is not approved")
	}
	digest := sha256.Sum256(body)
	if len(approved.SHA256) != 64 || hex.EncodeToString(digest[:]) != approved.SHA256 {
		return errors.New("distribution manifest is not the approved release")
	}
	keyring, err := openpgp.ReadArmoredKeyRing(bytes.NewReader(publicKey))
	if err != nil {
		return fmt.Errorf("invalid distribution public key: %w", err)
	}
	if len(keyring) != 1 || len(fingerprint) != 40 ||
		hex.EncodeToString(keyring[0].PrimaryKey.Fingerprint) != fingerprint ||
		fmt.Sprintf("%016x", keyring[0].PrimaryKey.KeyId) != keyID {
		return errors.New("distribution public key fingerprint does not match its pin")
	}
	_, err = openpgp.CheckDetachedSignatureAndHash(keyring,
		bytes.NewReader(block.Bytes), block.ArmoredSignature.Body,
		[]crypto.Hash{crypto.SHA256, crypto.SHA384, crypto.SHA512}, &packet.Config{})
	if err != nil {
		return fmt.Errorf("invalid distribution cryptographic signature: %w", err)
	}
	// The caller still executes all upstream file, ID/version, URL and unsigned
	// file checks; this function never marks a plugin valid by itself.
	return nil
}
