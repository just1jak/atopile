import app.freerouting.board.*;
import java.nio.file.*;
import java.util.*;

/** Deterministic safety checks; all changes are confined to disposable in-memory clones. */
public class TargetedRouteGuardTest {
  static void check(boolean condition) { if (!condition) throw new AssertionError(); }
  public static void main(String[] args) throws Exception {
    byte[] bytes = Files.readAllBytes(Paths.get("signals-stage/base-ground.ses.state.frb"));
    var original = TargetedRoute.read(bytes);
    var board = original.board();
    var counts = TargetedRoute.counts(board);
    var changed = new TreeMap<>(counts);
    int enable = board.rules.nets.get("EN", 1).net_number;
    changed.put(enable, counts.get(enable) + 1);
    check(!TargetedRoute.restored(board, counts, changed));
    changed = new TreeMap<>(counts);
    int ground = board.rules.nets.get("GND", 1).net_number;
    changed.put(ground, counts.get(ground) + 1);
    check(TargetedRoute.restored(board, counts, changed)); // GND is separately reported.
    int power = board.rules.nets.get("+3.3V", 1).net_number;
    var rules = board.rules.nets.get(power).get_class();
    int widthBefore = rules.get_trace_half_width(0);
    int[] widths = TargetedRoute.setWidth(original, power, 200);
    check(rules.get_trace_half_width(0) < widthBefore);
    TargetedRoute.restoreWidth(original, power, widths);
    for (int i = 0; i < widths.length; i++) check(rules.get_trace_half_width(i) == widths[i]);
    var fixed = GroundFanout.protectedItems(board);
    var traces = GroundFanout.tracePieces(board, true);
    var placement = GroundFanout.placements(board);
    var copy = TargetedRoute.read(TargetedRoute.serialize(original));
    check(TargetedRoute.preserved(copy.board(), fixed, traces, placement));
    Pin pin = copy.board().get_pins().iterator().next();
    int oldNet = pin.get_net_no(0);
    pin.assign_net_no(oldNet == ground ? power : ground);
    check(!TargetedRoute.preserved(copy.board(), fixed, traces, placement));
    check(board.get_item(pin.get_id_no()).get_net_no(0) == oldNet);
    System.out.println("5 targeted routing guard tests passed; source checkpoint unchanged");
  }
}
