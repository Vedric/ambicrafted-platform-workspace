// Build-only verification through the JVM's actual default trust manager.
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.TreeSet;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

class VerifyTrust {
    static final String REMOVED = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b";

    static String fingerprint(X509Certificate certificate) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded()));
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3 || !Arrays.asList("before", "after").contains(args[0])) {
            throw new IllegalArgumentException("before|after RECORD PUBLIC_ROOT");
        }
        var factory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        factory.init((java.security.KeyStore) null);
        X509TrustManager manager = null;
        for (TrustManager candidate : factory.getTrustManagers()) {
            if (candidate instanceof X509TrustManager) manager = (X509TrustManager) candidate;
        }
        if (manager == null) throw new IllegalStateException("Default JVM trust manager missing");
        var fingerprints = new TreeSet<String>();
        for (X509Certificate certificate : manager.getAcceptedIssuers()) fingerprints.add(fingerprint(certificate));
        X509Certificate root;
        try (var stream = Files.newInputStream(Path.of(args[2]))) {
            root = (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(stream);
        }
        if (!fingerprint(root).equals(REMOVED)) throw new IllegalStateException("Unqualified root fixture");
        boolean accepted;
        try {
            manager.checkServerTrusted(new X509Certificate[]{root}, "ECDHE_ECDSA");
            accepted = true;
        } catch (java.security.cert.CertificateException rejected) {
            accepted = false;
        }
        if (args[0].equals("before")) {
            if (!fingerprints.contains(REMOVED) || !accepted) throw new IllegalStateException("Expected positive trust control did not hold");
            Files.write(Path.of(args[1]), fingerprints);
        } else {
            var previous = new TreeSet<String>(Files.readAllLines(Path.of(args[1])));
            if (!previous.remove(REMOVED) || !previous.equals(fingerprints) || accepted) {
                throw new IllegalStateException("JVM trust policy differs beyond the exact distrusted root");
            }
        }
        System.out.printf("{\"stage\":\"%s\",\"default_java_roots\":%d,\"affected_root_trusted\":%s}%n", args[0], fingerprints.size(), accepted);
    }
}
