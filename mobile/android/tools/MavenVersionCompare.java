import java.io.BufferedReader;
import java.io.InputStreamReader;
import org.apache.maven.artifact.versioning.ComparableVersion;

// One tab-separated pair per line. No filesystem or network access.
class MavenVersionCompare {
    public static void main(String[] args) throws Exception {
        var input = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = input.readLine()) != null) {
            var pair = line.split("\t", -1);
            if (pair.length != 2 || pair[0].isBlank() || pair[1].isBlank()) {
                System.out.println("ERROR: expected two nonempty versions");
            } else {
                System.out.println(Integer.signum(new ComparableVersion(pair[0]).compareTo(new ComparableVersion(pair[1]))));
            }
            System.out.flush();
        }
    }
}
