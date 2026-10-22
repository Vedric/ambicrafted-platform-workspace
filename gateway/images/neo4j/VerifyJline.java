import org.jline.reader.impl.history.DefaultHistory;

/** Exercise the actual installed history matcher; no server or credentials. */
public class VerifyJline extends DefaultHistory {
    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    public static void main(String[] args) {
        var history = new VerifyJline();
        // Configuration is glob syntax, not an arbitrary regular expression.
        require(!history.matchPatterns("(a+)+b", "aaaaab"), "Regex syntax accepted");
        require(history.matchPatterns("(a+)+b", "(a+)+b"), "Literal syntax lost");
        require(history.matchPatterns("secret*:other", "secret value"), "Glob broken");
        require(history.matchPatterns("secret*:other", "other"), "Alternative broken");
        require(!history.matchPatterns("secret*:other", "unrelated"), "False match");
        require(!history.matchPatterns("(a+)+b", "a".repeat(100_000)), "Invalid match");
        var location = DefaultHistory.class.getProtectionDomain().getCodeSource()
            .getLocation().toString();
        require(location.endsWith("/jline-reader-3.30.15.jar"), "Unexpected JLine jar");
        System.out.println("JLine 3.30.15 literal/glob/history regression passed");
    }
}
