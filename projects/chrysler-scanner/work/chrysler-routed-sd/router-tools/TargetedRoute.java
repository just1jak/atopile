import app.freerouting.autoroute.*;
import app.freerouting.board.*;
import app.freerouting.datastructures.*;
import app.freerouting.designforms.specctra.SpecctraSesFileWriter;
import app.freerouting.interactive.*;
import app.freerouting.logger.FRLogger;
import app.freerouting.rules.Net;
import com.google.gson.Gson;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Small transactional signal repair on a trusted task-local core checkpoint. */
public final class TargetedRoute {
  static final List<String> TARGETS = List.of("VPP", "+3.3V", "PCI_TX", "V_PR", "RX2",
    "RX15_EN", "TX_LED", "ACT_LED", "LOG_BUTTON", "RX1", "VBB_TO_TX14");
  static final Gson JSON = new Gson();
  static boolean variedCosts;
  static final String SEARCH_PROFILE = System.getProperty("atopile.route.searchProfile", "standard");
  record State(RoutingBoard board, Settings settings) {}
  static class Budget implements Stoppable {
    final long deadline; boolean stop;
    Budget(int seconds) { deadline = System.nanoTime() + seconds * 1_000_000_000L; }
    public void request_stop() { stop = true; }
    public boolean is_stop_requested() { return stop || System.nanoTime() >= deadline; }
  }
  static byte[] serialize(State state) throws Exception {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
      out.writeObject(state.board); out.writeObject(state.settings);
    }
    return bytes.toByteArray();
  }
  static State read(byte[] bytes) throws Exception {
    try (ObjectInputStream in = new ObjectInputStream(new ByteArrayInputStream(bytes))) {
      in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
        "maxdepth=256;maxrefs=3000000;maxbytes=134217728;maxarray=3000000;*"));
      RoutingBoard board = (RoutingBoard) in.readObject();
      Settings settings = (Settings) in.readObject();
      board.set_test_level(TestLevel.RELEASE_VERSION);
      return new State(board, settings);
    }
  }
  static Map<Integer, Integer> counts(RoutingBoard board) {
    RatsNest nest = new RatsNest(board, Locale.ENGLISH);
    Map<Integer, Integer> counts = new TreeMap<>();
    for (int n = 1; n <= board.rules.nets.max_net_no(); n++) counts.put(n, nest.incomplete_count(n));
    return counts;
  }
  static Map<String, Integer> namedCounts(RoutingBoard board, Map<Integer, Integer> counts) {
    Map<String, Integer> result = new LinkedHashMap<>();
    for (String name : TARGETS) {
      Net net = board.rules.nets.get(name, 1);
      if (net == null) throw new IllegalArgumentException("Missing target net: " + name);
      result.put(name, counts.get(net.net_number));
    }
    return result;
  }
  static boolean preserved(RoutingBoard board, Map<Integer, String> items,
      List<GroundFanout.Piece> traces, List<String> placements) throws Exception {
    Map<Integer, String> afterItems = GroundFanout.protectedItems(board);
    for (var item : items.entrySet()) if (!item.getValue().equals(afterItems.get(item.getKey()))) return false;
    var afterTraces = GroundFanout.tracePieces(board, false).stream()
      .filter(p -> GroundFanout.covered(p, traces)).toList();
    return GroundFanout.sameCoverage(traces, afterTraces)
      && placements.equals(GroundFanout.placements(board));
  }
  static int violations(RoutingBoard board) { return new ClearanceViolations(board.get_items()).list.size(); }
  static int targetScore(RoutingBoard board, Map<Integer, Integer> counts) {
    return namedCounts(board, counts).values().stream().mapToInt(Integer::intValue).sum();
  }
  static int nonGroundScore(RoutingBoard board, Map<Integer, Integer> counts) {
    int score = 0;
    for (var n : counts.entrySet())
      if (!board.rules.nets.get(n.getKey()).name.equals("GND")) score += n.getValue();
    return score;
  }
  static Map<String, Integer> missingNonGround(RoutingBoard board, Map<Integer, Integer> counts) {
    Map<String, Integer> result = new LinkedHashMap<>();
    for (var n : counts.entrySet()) {
      String name = board.rules.nets.get(n.getKey()).name;
      if (!name.equals("GND") && n.getValue() > 0) result.put(name, n.getValue());
    }
    return result;
  }
  static boolean thinLogic(Net net) {
    if (TARGETS.contains(net.name) && !power(net.name)) return true;
    return net.get_class().get_name().equals("kicad_default")
      && !net.name.matches("(?i)(GND.*|.*GND|VCC.*|VDD.*|VSS.*|VBB.*|VPP.*|\\+.*|.*POWER.*|.*PWR.*)");
  }
  static boolean criticalRestored(RoutingBoard board, Map<Integer, Integer> baseline, Map<Integer, Integer> now) {
    for (var n : baseline.entrySet()) {
      String group = board.rules.nets.get(n.getKey()).get_class().get_name();
      if ((group.equals("rf_fixed") || group.equals("usb_fixed")) && now.get(n.getKey()) > n.getValue()) return false;
    }
    return true;
  }
  static boolean restored(RoutingBoard board, Map<Integer, Integer> baseline, Map<Integer, Integer> now) {
    for (var item : baseline.entrySet()) {
      String name = board.rules.nets.get(item.getKey()).name;
      if (!TARGETS.contains(name) && !name.equals("GND") && now.get(item.getKey()) > item.getValue()) return false;
    }
    return true;
  }
  static boolean power(String net) { return net.equals("+3.3V") || net.equals("VPP"); }
  static int[] setWidth(State s, int net, double widthUm) {
    var rules = s.board.rules.nets.get(net).get_class();
    int[] original = new int[s.board.get_layer_count()];
    int half = (int) Math.round(s.board.communication.coordinate_transform.dsn_to_board(widthUm / 2));
    for (int i = 0; i < original.length; i++) {
      original[i] = rules.get_trace_half_width(i); rules.set_trace_half_width(i, half);
    }
    return original;
  }
  static void restoreWidth(State s, int net, int[] widths) {
    var rules = s.board.rules.nets.get(net).get_class();
    for (int i = 0; i < widths.length; i++) rules.set_trace_half_width(i, widths[i]);
  }
  static double widthUm(RoutingBoard b, Trace t) {
    return b.communication.coordinate_transform.board_to_dsn(2.0 * t.get_half_width());
  }
  static double lengthMm(RoutingBoard b, Trace t) {
    return b.communication.coordinate_transform.board_to_dsn(t.get_length()) / 1000.0;
  }
  static AutorouteEngine.AutorouteResult fanoutBounded(State candidate, Pin pin,
      Budget budget, int milliseconds, boolean thin) throws Exception {
    int net = pin.get_net_no(0);
    String name = candidate.board.rules.nets.get(net).name;
    Set<String> sharedMcuPins = new HashSet<>();
    if (power(name)) for (Item item : pin.get_connected_set(net))
      if (item instanceof Pin member
          && candidate.board.components.get(member.get_component_no()).name.equals("U10"))
        sharedMcuPins.add(member.name());
    int[] widths = thin ? setWidth(candidate, net, power(name) ? 200 : 150) : null;
    List<GroundFanout.Piece> oldGeometry = GroundFanout.tracePieces(candidate.board, false);
    AutorouteEngine.AutorouteResult result;
    try {
      candidate.board.start_marking_changed_area();
      result = candidate.board.fanout(pin, candidate.settings, -1, budget, new TimeLimit(milliseconds));
      candidate.board.finish_autoroute();
    } finally { if (widths != null) restoreWidth(candidate, net, widths); }
    if (thin && power(name)) {
      double neckLength = 0;
      for (Trace trace : candidate.board.get_traces())
        if (trace.contains_net(net) && widthUm(candidate.board, trace) < 499.99)
          for (GroundFanout.Piece piece : GroundFanout.tracePieces(candidate.board, false)) {
            if (piece.id() != trace.get_id_no() || GroundFanout.covered(piece, oldGeometry)) continue;
            double length = piece.lo().to_float().distance(piece.hi().to_float());
            neckLength += candidate.board.communication.coordinate_transform.board_to_dsn(length) / 1000.0;
          }
      double limit = 3.0;
      String reference = candidate.board.components.get(pin.get_component_no()).name;
      if (name.equals("+3.3V")) {
        if (reference.equals("U10") || !sharedMcuPins.isEmpty()) limit = 4.0;
      }
      if (neckLength > limit + 0.0000001)
        throw new IOException("Power breakout exceeds reviewed local limit" + limit + "mm: " + neckLength);
    }
    return result;
  }
  static List<Map<String, Object>> thinTraces(RoutingBoard b) {
    List<Map<String, Object>> result = new ArrayList<>();
    for (Trace trace : b.get_traces()) {
      if (trace.net_count() != 1 || widthUm(b, trace) >= 499.99) continue;
      String net = b.rules.nets.get(trace.get_net_no(0)).name;
      if (!TARGETS.contains(net) && !(widthUm(b, trace) <= 150.00001
          && thinLogic(b.rules.nets.get(trace.get_net_no(0))))) continue;
      Map<String, Object> item = new LinkedHashMap<>();
      item.put("id", trace.get_id_no()); item.put("net", net);
      item.put("layer", b.layer_structure.arr[trace.get_layer()].name);
      item.put("widthMm", widthUm(b, trace) / 1000.0); item.put("lengthMm", lengthMm(b, trace));
      if (trace instanceof PolylineTrace p) {
        List<double[]> points = new ArrayList<>();
        for (var point : p.polyline().corner_arr()) {
          double[] xy = b.communication.coordinate_transform.board_to_dsn(point.to_float());
          points.add(new double[]{xy[0] / 1000, -xy[1] / 1000});
        }
        item.put("pointsMm", points);
      }
      result.add(item);
    }
    return result;
  }
  static AutorouteEngine.AutorouteResult route(State s, Pin pin, Budget budget, int milliseconds, int pass) {
    RoutingBoard board = s.board;
    int net = pin.get_net_no(0);
    var costs = s.settings.autoroute_settings.get_trace_cost_arr();
    int viaCosts = s.settings.autoroute_settings.get_via_costs();
    if (variedCosts) {
      viaCosts = pass % 3 == 2 ? 5 : pass % 3 == 0 ? 25 : 100;
      for (int i = 0; i < costs.length; i++)
        costs[i] = pass % 3 == 0 ? new AutorouteControl.ExpansionCostFactor(1, 1)
          : pass % 3 == 2 ? new AutorouteControl.ExpansionCostFactor(costs[i].vertical, costs[i].horizontal)
          : costs[i];
    }
    // Search preference only: active layers, widths and physical rules stay unchanged.
    if (!SEARCH_PROFILE.equals("standard")) {
      if (costs.length != 4 || !Set.of("inner", "back", "isotropic").contains(SEARCH_PROFILE))
        throw new IllegalArgumentException("Unsupported local search profile");
      for (int i=0;i<costs.length;i++) {
        double c = SEARCH_PROFILE.equals("isotropic") ? 1 : i==0 ? 8
          : SEARCH_PROFILE.equals("inner") ? (i==2 ? 1 : 3) : (i==3 ? 1 : 3);
        costs[i]=new AutorouteControl.ExpansionCostFactor(c,c);
      }
      viaCosts = 10;
    }
    AutorouteControl control = new AutorouteControl(board, net, s.settings, viaCosts, costs);
    control.remove_unconnected_vias = false;
    control.ripup_allowed = pass >= 2;
    control.ripup_costs = (variedCosts ? 500 : 10000) * (pass + 1);
    var start = pin.get_connected_set(net);
    var destination = pin.get_unconnected_set(net);
    if (destination.isEmpty()) return AutorouteEngine.AutorouteResult.ALREADY_CONNECTED;
    board.start_marking_changed_area();
    var engine = board.init_autoroute(net, control.trace_clearance_class_no, budget,
      new TimeLimit(milliseconds), false);
    var result = engine.autoroute_connection(start, destination, control, new TreeSet<Item>());
    if (result == AutorouteEngine.AutorouteResult.ROUTED)
      board.opt_changed_area(new int[0], null, s.settings.get_trace_pull_tight_accuracy(),
        control.trace_costs, budget, 1000);
    board.finish_autoroute();
    return result;
  }
  public static void main(String[] args) throws Exception {
    if (args.length != 5 && args.length != 6) throw new IllegalArgumentException(
      "Usage: TargetedRoute TRUSTED_CORE.frb NEW_OUTPUT.ses ORIGINAL.dsn PER_CONNECTION_MS TOTAL_SECONDS [thin-signals|thin-pass]");
    variedCosts = args.length == 6 && (args[5].equals("cost-pass") || args[5].equals("all-cost-pass"));
    boolean allMissing = args.length == 6 && (args[5].equals("all-pass") || args[5].equals("all-cost-pass"));
    boolean refine = args.length == 6 && (args[5].equals("refine-pass") || variedCosts || allMissing);
    boolean passLevel = args.length == 6 && (args[5].equals("thin-pass") || refine);
    boolean thin = args.length == 6 && (args[5].equals("thin-signals") || passLevel);
    if (args.length == 6 && !thin) throw new IllegalArgumentException("Unknown mode");
    int milliseconds = Integer.parseInt(args[3]), seconds = Integer.parseInt(args[4]);
    if (milliseconds < 1 || milliseconds > 5000 || seconds < 1 || seconds > 300)
      throw new IllegalArgumentException("Budgets exceed limits");
    Path jar = Paths.get(RoutingBoard.class.getProtectionDomain().getCodeSource().getLocation().toURI());
    if (!CheckpointToSes.sha(Files.readAllBytes(jar)).equals(
        "9084a4888937a7f31f857ecc12aa7a37407f51160e4d2892dff9c9bb47ae3102"))
      throw new IOException("Requires verified FreeRouting1.9 JAR");
    Path source = Paths.get(args[0]).toRealPath(), output = Paths.get(args[1]).toAbsolutePath();
    Path dsn = Paths.get(args[2]).toRealPath(), copy = Paths.get(output + ".input.frb");
    if (Files.exists(output) || Files.exists(copy) || Files.exists(Paths.get(output + ".state.frb"))
        || Files.exists(Paths.get(output + ".best.state.frb")))
      throw new IOException("Outputs must be new paths");
    byte[] bytes = CheckpointToSes.stableCopy(source, copy);
    FRLogger.disableLogging();
    State best = read(bytes);
    final RoutingBoard initialBoard = best.board;
    // Native seed locks are SYSTEM_FIXED; USER_FIXED is protected too. SHOVE_FIXED
    // is the router's transient state and can be changed only without regressions.
    Map<Integer, String> fixed = GroundFanout.protectedItems(best.board);
    fixed.entrySet().removeIf(e -> initialBoard.get_item(e.getKey()).get_fixed_state() == FixedState.SHOVE_FIXED);
    List<GroundFanout.Piece> fixedTraces = GroundFanout.tracePieces(best.board, true).stream()
      .filter(p -> initialBoard.get_item(p.id()).get_fixed_state() != FixedState.SHOVE_FIXED).toList();
    List<String> placements = GroundFanout.placements(best.board);
    Map<Integer, Integer> bestCounts = counts(best.board);
    Map<Integer, Integer> baselineCounts = new TreeMap<>(bestCounts);
    Map<String, Integer> initial = namedCounts(best.board, bestCounts);
    int bestViolations = violations(best.board), attempts = 0, accepted = 0;
    Budget budget = new Budget(seconds);
    byte[] bestBytes = serialize(best);
    byte[] approvedBytes = bestBytes;
    int approvedScore = nonGroundScore(best.board, bestCounts);
    System.out.println(JSON.toJson(Map.of("initial", initial, "engineViolations", bestViolations)));
    for (int pass = refine ? 2 : 0; pass < (refine ? 5 : 3) && !budget.is_stop_requested(); pass++) {
      List<String> netOrder = new ArrayList<>(TARGETS);
      if (allMissing) for (String missing : missingNonGround(best.board, bestCounts).keySet())
        if (!netOrder.contains(missing)) netOrder.add(missing);
      if ((pass & 1) == 1 && refine) Collections.reverse(netOrder);
      for (String name : netOrder) {
        if (budget.is_stop_requested()) break;
        Net net = best.board.rules.nets.get(name, 1);
        if (bestCounts.get(net.net_number) == 0) continue;
        List<Pin> pins = new ArrayList<>(net.get_pins());
        final int netNo = net.net_number;
        pins.sort(Comparator.comparingInt((Pin p) -> p.get_connected_set(netNo).size())
          .thenComparingInt(p -> p.get_component_no()).thenComparingInt(p -> p.pin_no));
        Set<String> triedSets = new HashSet<>();
        for (Pin oldPin : pins) {
          if (budget.is_stop_requested() || bestCounts.get(netNo) == 0) break;
          State candidate = read(bestBytes);
          Pin pin = (Pin) candidate.board.get_item(oldPin.get_id_no());
          if (pin == null) continue;
          String set = pin.get_connected_set(netNo).stream().map(Item::get_id_no).sorted().toList().toString();
          if (!triedSets.add(set)) continue;
          int before = bestCounts.get(netNo), viasBefore = candidate.board.get_vias().size();
          String reference = candidate.board.components.get(pin.get_component_no()).name;
          var fanout = AutorouteEngine.AutorouteResult.ALREADY_CONNECTED;
          var outcome = AutorouteEngine.AutorouteResult.NOT_ROUTED;
          String rejected = null;
          try {
            if (pass >= 1 && pin.first_layer() == pin.last_layer()) {
              fanout = fanoutBounded(candidate, pin, budget, milliseconds,
                thin && (power(name) || thinLogic(candidate.board.rules.nets.get(netNo))));
            }
            if (!budget.is_stop_requested()) {
              int[] widths = thin && thinLogic(candidate.board.rules.nets.get(netNo))
                ? setWidth(candidate, netNo, 150) : null;
              try { outcome = route(candidate, pin, budget, milliseconds, pass); }
              finally { if (widths != null) restoreWidth(candidate, netNo, widths); }
            }
            Map<Integer, Integer> candidateCounts = counts(candidate.board);
            if (!passLevel) for (var count : bestCounts.entrySet())
              if (candidateCounts.get(count.getKey()) > count.getValue()) { rejected = "net connectivity regression"; break; }
            boolean useful = candidateCounts.get(netNo) < before
              || (pass == 1 && candidate.board.get_vias().size() > viasBefore);
            if (rejected == null && !useful) rejected = "no improvement or new escape via";
            if (rejected == null && !preserved(candidate.board, fixed, fixedTraces, placements)) rejected = "protected geometry changed";
            int candidateViolations = rejected == null ? violations(candidate.board) : bestViolations;
            if (rejected == null && candidateViolations > bestViolations) rejected = "engine clearance regression";
            if (rejected == null) {
              best = candidate; bestCounts = candidateCounts; bestViolations = candidateViolations;
              bestBytes = serialize(best); accepted++;
            }
          } catch (Exception error) { rejected = error.getClass().getSimpleName() + ": " + error.getMessage(); }
          attempts++;
          Map<String, Object> report = new LinkedHashMap<>();
          report.put("pass", pass + 1); report.put("net", name); report.put("reference", reference);
          report.put("pin", pin.name()); report.put("fanout", fanout); report.put("route", outcome);
          report.put("before", before); report.put("after", bestCounts.get(netNo));
          report.put("accepted", rejected == null); report.put("rejected", rejected);
          System.out.println(JSON.toJson(report));
        }
      }
      if (passLevel) {
        // A pass is a transaction. Reconnect displaced unprotected copper before
        // approving any snapshot; never export the temporary disconnected state.
        for (int repairRound = 0; repairRound < 16 && !budget.is_stop_requested(); repairRound++) {
          List<Integer> displaced = new ArrayList<>();
          for (var count : baselineCounts.entrySet())
            if (!best.board.rules.nets.get(count.getKey()).name.equals("GND")
                && bestCounts.get(count.getKey()) > count.getValue()) displaced.add(count.getKey());
          if (displaced.isEmpty()) break;
          boolean repaired = false;
          for (int displacedNo : displaced) {
            if (budget.is_stop_requested()) break;
            State candidate = read(bestBytes);
            Net net = candidate.board.rules.nets.get(displacedNo);
            List<Pin> displacedPins = new ArrayList<>(net.get_pins());
            displacedPins.sort(Comparator.comparingInt(p -> p.get_connected_set(displacedNo).size()));
            Set<String> triedComponents = new HashSet<>();
            for (Pin pin : displacedPins) {
              if (budget.is_stop_requested()) break;
              Pin activePin = (Pin) candidate.board.get_item(pin.get_id_no());
              String component = activePin.get_connected_set(displacedNo).stream()
                .map(Item::get_id_no).sorted().toList().toString();
              if (!triedComponents.add(component)) continue;
              if (thin && power(net.name) && activePin.first_layer() == activePin.last_layer()) {
                try { fanoutBounded(candidate, activePin, budget, milliseconds, true); }
                catch (Exception rejectedNeck) { candidate = read(bestBytes); continue; }
              }
              int[] widths = thin && thinLogic(net)
                ? setWidth(candidate, displacedNo, 150) : null;
              AutorouteEngine.AutorouteResult outcome;
              try { outcome = route(candidate, activePin, budget, milliseconds, 2); }
              finally { if (widths != null) restoreWidth(candidate, displacedNo, widths); }
              Map<Integer, Integer> candidateCounts = counts(candidate.board);
              int countBefore = bestCounts.get(displacedNo);
              boolean acceptedRepair = candidateCounts.get(displacedNo) < countBefore
                && preserved(candidate.board, fixed, fixedTraces, placements)
                && violations(candidate.board) <= bestViolations;
              System.out.println(JSON.toJson(Map.of("repairRound", repairRound + 1, "net", net.name,
                "route", outcome.toString(), "before", countBefore,
                "after", candidateCounts.get(displacedNo), "accepted", acceptedRepair)));
              if (acceptedRepair) {
                best = candidate; bestCounts = candidateCounts; bestBytes = serialize(best);
                bestViolations = violations(best.board); repaired = true; accepted++;
                break;
              }
              candidate = read(bestBytes);
            }
          }
          if (!repaired) break;
        }
        boolean restorePassed = restored(best.board, baselineCounts, bestCounts);
        int score = nonGroundScore(best.board, bestCounts);
        if (criticalRestored(best.board, baselineCounts, bestCounts) && score < approvedScore) {
          approvedBytes = bestBytes; approvedScore = score;
          Files.write(Paths.get(output + ".best.state.frb"), approvedBytes,
            StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
          try (OutputStream checkpoint = Files.newOutputStream(
              Paths.get(output + ".pass-" + (pass + 1) + ".ses"), StandardOpenOption.CREATE_NEW)) {
            if (!SpecctraSesFileWriter.write(best.board, checkpoint, dsn.getFileName().toString()))
              throw new IOException("Intermediate SES export failed");
          }
        }
        System.out.println(JSON.toJson(Map.of("passComplete", pass + 1,
          "nonGroundMissing", score, "nonTargetRestored", restorePassed,
          "approvedNonGroundMissing", approvedScore,
          "queuedMissingNets", missingNonGround(best.board, bestCounts))));
      }
    }
    if (passLevel && !restored(best.board, baselineCounts, bestCounts)) {
      // Diagnostic continuation only: never export an SES from this disconnected state.
      Files.write(Paths.get(output + ".UNAPPROVED-working.core.frb"), bestBytes, StandardOpenOption.CREATE_NEW);
      Files.writeString(Paths.get(output + ".UNAPPROVED-counts.json"), JSON.toJson(namedCounts(best.board, bestCounts)),
        StandardOpenOption.CREATE_NEW);
    }
    if (passLevel) { best = read(approvedBytes); bestCounts = counts(best.board); bestBytes = approvedBytes;
      bestViolations = violations(best.board); }
    Map<String, Integer> result = namedCounts(best.board, bestCounts);
    boolean improved = nonGroundScore(best.board, bestCounts) < nonGroundScore(best.board, baselineCounts);
    if (improved) {
      if (!preserved(best.board, fixed, fixedTraces, placements)) throw new IOException("Final preservation guard failed");
      try (OutputStream out = Files.newOutputStream(output, StandardOpenOption.CREATE_NEW)) {
        if (!SpecctraSesFileWriter.write(best.board, out, dsn.getFileName().toString())) throw new IOException("SES writer failed");
      }
      Files.write(Paths.get(output + ".state.frb"), bestBytes, StandardOpenOption.CREATE_NEW);
      Files.writeString(Paths.get(output + ".thin-traces.json"), JSON.toJson(thinTraces(best.board)),
        StandardOpenOption.CREATE_NEW);
    }
    Map<String, Object> summary = new LinkedHashMap<>();
    summary.put("summary", true); summary.put("inputSha256", CheckpointToSes.sha(bytes));
    summary.put("initial", initial); summary.put("final", result); summary.put("improved", improved);
    summary.put("allRemainingNonGroundNets", missingNonGround(best.board, bestCounts));
    summary.put("beforeNonGroundMissing", nonGroundScore(best.board, baselineCounts));
    summary.put("afterNonGroundMissing", nonGroundScore(best.board, bestCounts));
    summary.put("attempts", attempts); summary.put("accepted", accepted);
    summary.put("engineAirwires", new RatsNest(best.board, Locale.ENGLISH).incomplete_count());
    summary.put("engineViolations", bestViolations);
    summary.put("nonTargetConnectivityPreserved", restored(best.board, baselineCounts, bestCounts));
    summary.put("groundBefore", baselineCounts.get(best.board.rules.nets.get("GND", 1).net_number));
    summary.put("groundAfter", bestCounts.get(best.board.rules.nets.get("GND", 1).net_number));
    summary.put("protectedItemsPreserved", fixed.size()); summary.put("placementsPreserved", placements.size());
    summary.put("exactFixedCenterlineCoverage", true); summary.put("timeBudgetReached", budget.is_stop_requested());
    System.out.println(JSON.toJson(summary));
  }
}
