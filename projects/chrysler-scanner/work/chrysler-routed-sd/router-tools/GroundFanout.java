import app.freerouting.board.*;
import app.freerouting.datastructures.*;
import app.freerouting.designforms.specctra.SpecctraSesFileWriter;
import app.freerouting.interactive.*;
import app.freerouting.logger.FRLogger;
import app.freerouting.rules.Net;
import app.freerouting.geometry.planar.Point;
import app.freerouting.geometry.planar.Side;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Bounded GND-only fanout of a copied checkpoint; never touches a native PCB/live engine. */
public final class GroundFanout {
  private static final String JAR_SHA = "9084a4888937a7f31f857ecc12aa7a37407f51160e4d2892dff9c9bb47ae3102";
  private static class Budget implements Stoppable {
    final long deadline;
    boolean stopped;
    Budget(int seconds) { deadline = System.nanoTime() + seconds * 1_000_000_000L; }
    public void request_stop() { stopped = true; }
    public boolean is_stop_requested() { return stopped || System.nanoTime() >= deadline; }
  }
  private static String geometry(Object geometry) throws Exception {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    try (ObjectOutputStream out = new ObjectOutputStream(bytes)) { out.writeObject(geometry); }
    return CheckpointToSes.sha(bytes.toByteArray());
  }
  static Map<Integer, String> protectedItems(RoutingBoard board) throws Exception {
    Map<Integer, String> result = new TreeMap<>();
    for (Item item : board.get_items()) {
      if (item.get_fixed_state() == FixedState.UNFIXED && !(item instanceof Pin)) continue;
      if (item instanceof PolylineTrace) continue; // Verified separately by exact centerline coverage.
      String signature = item.getClass().getName() + ":" + item.get_fixed_state() + ":"
          + item.first_layer() + ":" + item.last_layer() + ":" + item.get_component_no()
          + ":" + item.clearance_class_no();
      for (int n = 0; n < item.net_count(); n++) signature += ":net" + item.get_net_no(n);
      if (item instanceof DrillItem drill)
        signature += ":" + geometry(drill.get_center()) + ":" + drill.get_padstack().name;
      else if (item instanceof ObstacleArea area)
        signature += ":" + geometry(area.get_area());
      else if (item instanceof BoardOutline outline)
        signature += ":" + geometry(outline.bounding_box());
      result.put(item.get_id_no(), signature);
    }
    return result;
  }
  record Piece(int id, String key, Point lo, Point hi) {
    Piece {
      if (lo.compare_x_y(hi) > 0) { Point swap = lo; lo = hi; hi = swap; }
    }
  }
  static List<Piece> tracePieces(RoutingBoard board, boolean fixedOnly) {
    List<Piece> result = new ArrayList<>();
    for (Trace item : board.get_traces()) {
      if (fixedOnly && item.get_fixed_state() == FixedState.UNFIXED) continue;
      if (!(item instanceof PolylineTrace trace)) throw new IllegalStateException("Unsupported fixed trace");
      // Junction insertion can change a split piece's internal fixed classification.
      // Preserve physical layer/net/width/clearance and exact rational geometry instead.
      String key = trace.get_layer() + ":" + trace.get_half_width()
        + ":" + trace.clearance_class_no() + ":" + trace.get_component_no();
      for (int n = 0; n < trace.net_count(); n++) key += ":net" + trace.get_net_no(n);
      Point[] points = trace.polyline().corner_arr();
      for (int i = 1; i < points.length; i++)
        if (!points[i - 1].equals(points[i]))
          result.add(new Piece(trace.get_id_no(), key, points[i - 1], points[i]));
    }
    return result;
  }
  static boolean covered(Piece wanted, List<Piece> candidates) {
    List<Piece> matching = new ArrayList<>();
    for (Piece p : candidates)
      if (wanted.key.equals(p.key)
          && p.lo.side_of(wanted.lo, wanted.hi) == Side.COLLINEAR
          && p.hi.side_of(wanted.lo, wanted.hi) == Side.COLLINEAR
          && p.hi.compare_x_y(wanted.lo) >= 0 && p.lo.compare_x_y(wanted.hi) <= 0)
        matching.add(p);
    matching.sort((a, b) -> a.lo.compare_x_y(b.lo));
    Point end = wanted.lo;
    for (Piece p : matching) {
      if (p.lo.compare_x_y(end) > 0) return false;
      if (p.hi.compare_x_y(end) > 0) end = p.hi;
      if (end.compare_x_y(wanted.hi) >= 0) return true;
    }
    return false;
  }
  static boolean sameCoverage(List<Piece> before, List<Piece> after) {
    return before.stream().allMatch(p -> covered(p, after))
      && after.stream().allMatch(p -> covered(p, before));
  }
  static List<String> placements(RoutingBoard board) throws Exception {
    List<String> result = new ArrayList<>();
    for (int i = 1; i <= board.components.count(); i++) {
      Component c = board.components.get(i);
      result.add(c.name + ":" + geometry(c.get_location()) + ":" + c.get_rotation_in_degree()
          + ":" + c.placed_on_front() + ":" + c.get_package().name);
    }
    return result;
  }
  private static boolean reachesPlane(Pin pin, int net) {
    return pin.get_connected_set(net).stream().anyMatch(item -> item instanceof ConductionArea);
  }
  public static void main(String[] args) throws Exception {
    if (args.length != 5) throw new IllegalArgumentException(
      "Usage: GroundFanout TRUSTED_LOCAL.frb NEW_OUTPUT.ses ORIGINAL.dsn PER_PIN_MS TOTAL_SECONDS");
    int perPin = Integer.parseInt(args[3]), seconds = Integer.parseInt(args[4]);
    if (perPin < 1 || perPin > 5000 || seconds < 1 || seconds > 300)
      throw new IllegalArgumentException("Budgets must be 1..5000ms per pin and 1..300seconds total");
    Path jar = Paths.get(RoutingBoard.class.getProtectionDomain().getCodeSource().getLocation().toURI());
    if (!CheckpointToSes.sha(Files.readAllBytes(jar)).equals(JAR_SHA))
      throw new IOException("Requires verified FreeRouting1.9 JAR");
    Path source = Paths.get(args[0]).toRealPath(), output = Paths.get(args[1]).toAbsolutePath();
    Path dsn = Paths.get(args[2]).toRealPath(), copy = Paths.get(output + ".input.frb");
    if (Files.exists(output) || Files.exists(copy)) throw new IOException("Outputs must be new paths");
    byte[] bytes = CheckpointToSes.stableCopy(source, copy);
    FRLogger.disableLogging();
    RoutingBoard board;
    Settings settings;
    try (ObjectInputStream in = new ObjectInputStream(new ByteArrayInputStream(bytes))) {
      in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
        "maxdepth=256;maxrefs=3000000;maxbytes=134217728;maxarray=3000000;*"));
      board = (RoutingBoard) in.readObject(); settings = (Settings) in.readObject();
    }
    board.set_test_level(TestLevel.RELEASE_VERSION);
    Net ground = board.rules.nets.get("GND", 1);
    if (ground == null || !ground.contains_plane()) throw new IOException("No recognized GND plane");
    Map<Integer, String> fixed = protectedItems(board);
    List<Piece> fixedTraces = tracePieces(board, true);
    List<String> components = placements(board);
    int before = new RatsNest(board, Locale.ENGLISH).incomplete_count();
    RatsNest beforeNets = new RatsNest(board, Locale.ENGLISH);
    Map<Integer, Integer> otherNetAirwires = new HashMap<>();
    for (int n = 1; n <= board.rules.nets.max_net_no(); n++)
      if (n != ground.net_number) otherNetAirwires.put(n, beforeNets.incomplete_count(n));
    int groundBefore = new RatsNest(board, Locale.ENGLISH).incomplete_count(ground.net_number);
    int viasBefore = board.get_vias().size(), attempts = 0, routed = 0;
    List<Pin> pins = new ArrayList<>(ground.get_pins());
    pins.sort(Comparator.comparingInt((Pin p) -> p.get_component_no()).thenComparingInt(p -> p.pin_no));
    Budget budget = new Budget(seconds);
    for (int pass = 1; pass <= 2 && !budget.is_stop_requested(); pass++) {
      int passRouted = 0;
      for (Pin pin : pins) {
        if (budget.is_stop_requested()) break;
        if (pin.first_layer() != pin.last_layer() || reachesPlane(pin, ground.net_number)) continue;
        board.start_marking_changed_area();
        var outcome = board.fanout(pin, settings, -1, budget, new TimeLimit(perPin));
        attempts++;
        if (outcome == app.freerouting.autoroute.AutorouteEngine.AutorouteResult.ROUTED) {
          routed++; passRouted++;
        }
        System.out.printf(Locale.ROOT,
          "{\"pass\":%d,\"reference\":\"%s\",\"pin\":\"%s\",\"result\":\"%s\",\"reachesPlane\":%s}%n",
          pass, board.components.get(pin.get_component_no()).name, pin.name(), outcome,
          reachesPlane(pin, ground.net_number));
      }
      if (passRouted == 0) break;
    }
    board.finish_autoroute();
    Map<Integer, String> afterItems = protectedItems(board);
    for (var entry : fixed.entrySet())
      if (!entry.getValue().equals(afterItems.get(entry.getKey())))
        throw new IOException("Protected item changed: " + entry.getKey() + "; before=" + entry.getValue()
            + "; after=" + afterItems.get(entry.getKey()) + "; candidate not exported");
    // Accept only after-pieces wholly contained in the original protected centerlines.
    // A longer/shifted/wider substitute never qualifies, even if it crosses an old endpoint.
    List<Piece> afterTraces = tracePieces(board, false).stream()
      .filter(p -> covered(p, fixedTraces)).toList();
    if (!sameCoverage(fixedTraces, afterTraces)) {
      for (Piece p : fixedTraces) {
        if (covered(p, afterTraces)) continue;
        System.err.printf("uncovered oldid=%d key=%s endpoints=%s -> %s%n", p.id, p.key,
          p.lo.to_float(), p.hi.to_float());
        for (Piece q : tracePieces(board, false)) {
          if (q.lo.side_of(p.lo, p.hi) == Side.COLLINEAR && q.hi.side_of(p.lo, p.hi) == Side.COLLINEAR
              && q.hi.compare_x_y(p.lo) >= 0 && q.lo.compare_x_y(p.hi) <= 0)
            System.err.printf("  collinear afterid=%d key=%s endpoints=%s -> %s%n", q.id, q.key,
              q.lo.to_float(), q.hi.to_float());
        }
      }
      throw new IOException("Fixed trace centerline/layer/net/width coverage changed; candidate not exported");
    }
    for (Piece p : fixedTraces) {
      if (board.get_item(p.id) != null) continue;
      List<Integer> ids = afterTraces.stream().filter(q -> q.key.equals(p.key)
        && q.lo.side_of(p.lo, p.hi) == Side.COLLINEAR && q.hi.side_of(p.lo, p.hi) == Side.COLLINEAR
        && q.hi.compare_x_y(p.lo) >= 0 && q.lo.compare_x_y(p.hi) <= 0).map(q -> q.id).distinct().toList();
      System.out.printf("{\"subdividedFixedTraceId\":%d,\"exactCoverageVerified\":true,\"coveringTraceIds\":%s}%n", p.id, ids);
    }
    if (!components.equals(placements(board))) throw new IOException("Placement changed; candidate not exported");
    int after = new RatsNest(board, Locale.ENGLISH).incomplete_count();
    RatsNest afterNets = new RatsNest(board, Locale.ENGLISH);
    for (var net : otherNetAirwires.entrySet())
      if (afterNets.incomplete_count(net.getKey()) > net.getValue())
        throw new IOException("Non-GND net connectivity regressed: " + net.getKey());
    int groundAfter = new RatsNest(board, Locale.ENGLISH).incomplete_count(ground.net_number);
    Path temp = Files.createTempFile(output.getParent(), ".ground-fanout-", ".tmp");
    try {
      try (OutputStream out = Files.newOutputStream(temp)) {
        if (!SpecctraSesFileWriter.write(board, out, dsn.getFileName().toString()))
          throw new IOException("SES export failed");
      }
      Files.move(temp, output);
    } finally { Files.deleteIfExists(temp); }
    // Task-local core continuation state, not the GUI FRB format (only two objects).
    try (ObjectOutputStream state = new ObjectOutputStream(Files.newOutputStream(
        Paths.get(output + ".state.frb"), StandardOpenOption.CREATE_NEW))) {
      state.writeObject(board); state.writeObject(settings);
    }
    System.out.printf(Locale.ROOT,
      "{\"summary\":true,\"inputSha256\":\"%s\",\"attempts\":%d,\"routed\":%d,"
      + "\"beforeAirwires\":%d,\"afterAirwires\":%d,\"groundBefore\":%d,\"groundAfter\":%d,"
      + "\"viasBefore\":%d,\"viasAfter\":%d,\"protectedItemsPreserved\":%d,\"placementsPreserved\":%d,"
      + "\"exactFixedCenterlineCoverage\":true,\"timeBudgetReached\":%s}%n", CheckpointToSes.sha(bytes), attempts, routed, before, after,
      groundBefore, groundAfter, viasBefore, board.get_vias().size(), fixed.size(), components.size(),
      budget.is_stop_requested());
  }
}
