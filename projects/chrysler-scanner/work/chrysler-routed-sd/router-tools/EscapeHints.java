import app.freerouting.board.*;
import app.freerouting.interactive.RatsNest;
import app.freerouting.rules.Net;
import java.nio.file.*;
import java.util.*;

/** Read-only local pin-to-via geometry from another immutable engine snapshot. */
public class EscapeHints {
  record Search(Item item, double length, List<Item> path) {}
  static Pin pin(RoutingBoard board, String reference, String number) {
    return board.get_pins().stream().filter(p -> board.components.get(p.get_component_no()).name.equals(reference)
      && p.name().equals(number)).findFirst().orElseThrow();
  }
  static double[] xy(RoutingBoard board, app.freerouting.geometry.planar.Point point) {
    double[] value = board.communication.coordinate_transform.board_to_dsn(point.to_float());
    return new double[]{value[0] / 1000, -value[1] / 1000};
  }
  static Map<String, Object> trace(RoutingBoard board, PolylineTrace trace) {
    List<double[]> points = new ArrayList<>();
    for (var p : trace.polyline().corner_arr()) points.add(xy(board, p));
    return Map.of("kind", "trace", "id", trace.get_id_no(), "layer",
      board.layer_structure.arr[trace.get_layer()].name, "widthMm",
      TargetedRoute.widthUm(board, trace) / 1000, "pointsMm", points);
  }
  public static void main(String[] args) throws Exception {
    var current = TargetedRoute.read(Files.readAllBytes(Paths.get(args[0]))).board();
    var alternate = TargetedRoute.read(Files.readAllBytes(Paths.get(args[1]))).board();
    List<Map<String, Object>> result = new ArrayList<>();
    for (String identity : List.of("U10:16", "U10:11", "U19:15", "U10:6", "U10:33",
        "U19:16", "U10:10", "U10:15", "U10:5")) {
      String[] parts = identity.split(":");
      Pin before = pin(current, parts[0], parts[1]), start = pin(alternate, parts[0], parts[1]);
      String name = current.rules.nets.get(before.get_net_no(0)).name;
      Net net = alternate.rules.nets.get(name, 1);
      if (net == null || !start.contains_net(net.net_number)) throw new IllegalStateException("Pin/net mismatch");
      double[] oldXY = xy(current, before.get_center()), newXY = xy(alternate, start.get_center());
      if (Math.hypot(oldXY[0] - newXY[0], oldXY[1] - newXY[1]) > 0.00011)
        throw new IllegalStateException("Different pin placement");
      PriorityQueue<Search> queue = new PriorityQueue<>(Comparator.comparingDouble(Search::length));
      queue.add(new Search(start, 0, List.of(start)));
      Set<Integer> visited = new HashSet<>();
      Search found = null;
      while (!queue.isEmpty() && visited.size() < 128) {
        Search state = queue.poll();
        if (!visited.add(state.item.get_id_no())) continue;
        if (state.item instanceof Via) { found = state; break; }
        if (!(state.item instanceof Connectable connectable)) continue;
        for (Item next : connectable.get_normal_contacts()) {
          if (!next.contains_net(net.net_number) || visited.contains(next.get_id_no())) continue;
          if (next instanceof Pin || next instanceof ConductionArea) continue;
          double length = state.length + (next instanceof Trace t ? TargetedRoute.lengthMm(alternate, t) : 0);
          if (length > 6) continue;
          List<Item> path = new ArrayList<>(state.path); path.add(next);
          queue.add(new Search(next, length, path));
        }
      }
      Map<String, Object> hint = new LinkedHashMap<>();
      hint.put("reference", parts[0]); hint.put("pin", parts[1]); hint.put("net", name);
      hint.put("pinMm", newXY);
      hint.put("alternateNetComplete", new RatsNest(alternate, Locale.ENGLISH).incomplete_count(net.net_number) == 0);
      hint.put("currentNetMissing", new RatsNest(current, Locale.ENGLISH).incomplete_count(before.get_net_no(0)));
      hint.put("validatedAgainstCurrentCopper", false);
      List<Map<String, Object>> firstContacts = new ArrayList<>();
      for (Item contact : start.get_normal_contacts())
        if (contact instanceof PolylineTrace trace) firstContacts.add(trace(alternate, trace));
      hint.put("firstContactTraces", firstContacts);
      List<Map<String, Object>> items = new ArrayList<>();
      if (found != null) {
        hint.put("pathLengthMm", found.length);
        for (Item item : found.path) {
          if (item instanceof PolylineTrace trace) {
            items.add(trace(alternate, trace));
          } else if (item instanceof Via via)
            items.add(Map.of("kind", "via", "id", item.get_id_no(), "positionMm",
              xy(alternate, via.get_center()), "padstack", via.get_padstack().name));
        }
      }
      hint.put("items", items); result.add(hint);
    }
    Files.writeString(Paths.get(args[2]), TargetedRoute.JSON.toJson(Map.of(
      "kind", "READ_ONLY_ALTERNATE_ENGINE_HINTS", "nativeCollisionValidationRequired", true,
      "hints", result)), StandardOpenOption.CREATE_NEW);
    System.out.println("Exported9read-onlypin-to-viahints; no copper imported or changed");
  }
}
