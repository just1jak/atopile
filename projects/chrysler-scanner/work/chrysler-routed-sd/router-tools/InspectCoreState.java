import app.freerouting.board.*;
import app.freerouting.rules.Net;
import java.nio.file.*;
import java.util.*;

/** Read-only accounting for every net, including displaced non-target nets. */
public class InspectCoreState {
  public static void main(String[] args) throws Exception {
    var before = TargetedRoute.read(Files.readAllBytes(Paths.get(args[0])));
    var after = TargetedRoute.read(Files.readAllBytes(Paths.get(args[1])));
    var oldCounts = TargetedRoute.counts(before.board());
    var newCounts = TargetedRoute.counts(after.board());
    List<Map<String, Object>> missing = new ArrayList<>(), changed = new ArrayList<>();
    int oldTotal = 0, newTotal = 0;
    for (int n = 1; n <= before.board().rules.nets.max_net_no(); n++) {
      Net net = before.board().rules.nets.get(n);
      int old = oldCounts.get(n), current = newCounts.get(n);
      if (!net.name.equals("GND")) { oldTotal += old; newTotal += current; }
      if (current > 0) missing.add(Map.of("net", net.name, "missing", current));
      if (old != current) changed.add(Map.of("net", net.name, "before", old, "after", current));
    }
    Map<Integer, String> fixed = GroundFanout.protectedItems(before.board());
    fixed.entrySet().removeIf(e -> before.board().get_item(e.getKey()).get_fixed_state() == FixedState.SHOVE_FIXED);
    var traces = GroundFanout.tracePieces(before.board(), true).stream()
      .filter(p -> before.board().get_item(p.id()).get_fixed_state() != FixedState.SHOVE_FIXED).toList();
    boolean preserved = TargetedRoute.preserved(after.board(), fixed, traces, GroundFanout.placements(before.board()));
    System.out.println(TargetedRoute.JSON.toJson(Map.of("beforeNonGround", oldTotal,
      "afterNonGround", newTotal, "missing", missing, "changed", changed,
      "protectedGeometryPreserved", preserved,
      "beforeEngineViolations", TargetedRoute.violations(before.board()),
      "afterEngineViolations", TargetedRoute.violations(after.board()))));
  }
}
