import app.freerouting.geometry.planar.Point;
import java.math.BigInteger;
import java.util.List;

/** Exact geometric safety checks, independent of an actual board or router. */
public class GroundFanoutCoverageTest {
  static GroundFanout.Piece p(int id, String key, int x1, int y1, int x2, int y2) {
    return new GroundFanout.Piece(id, key, Point.get_instance(x1, y1), Point.get_instance(x2, y2));
  }
  static void check(boolean condition) { if (!condition) throw new AssertionError(); }
  public static void main(String[] args) {
    var original = List.of(p(1, "F:GND:350", 0, 0, 1000, 1000));
    check(GroundFanout.sameCoverage(original, List.of(
      p(2, "F:GND:350", 0, 0, 375, 375), p(3, "F:GND:350", 1000, 1000, 375, 375))));
    check(!GroundFanout.sameCoverage(original, List.of(
      p(2, "F:GND:350", 0, 0, 375, 375), p(3, "F:GND:350", 376, 376, 1000, 1000))));
    check(!GroundFanout.sameCoverage(original, List.of(p(2, "F:GND:350", 0, 1, 1000, 1001))));
    check(!GroundFanout.sameCoverage(original, List.of(p(2, "B:GND:350", 0, 0, 1000, 1000))));
    check(!GroundFanout.sameCoverage(original, List.of(p(2, "F:GND:349", 0, 0, 1000, 1000))));
    check(!GroundFanout.sameCoverage(original, List.of(p(2, "F:GND:350", 0, 0, 1001, 1001))));
    Point third = Point.get_instance(BigInteger.ONE, BigInteger.ONE, BigInteger.valueOf(3));
    check(GroundFanout.sameCoverage(original, List.of(
      new GroundFanout.Piece(2, "F:GND:350", Point.ZERO, third),
      new GroundFanout.Piece(3, "F:GND:350", third, Point.get_instance(1000, 1000)))));
    System.out.println("7 exact fixed-trace coverage tests passed");
  }
}
