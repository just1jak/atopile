import app.freerouting.autoroute.*;
import app.freerouting.board.*;
import app.freerouting.designforms.specctra.SpecctraSesFileWriter;
import app.freerouting.interactive.*;
import app.freerouting.rules.Net;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Bounded, guarded use of an alternate local escape; native files are never edited. */
public class AnchoredEscape {
  static List<Item> escape(RoutingBoard board, Pin pin, int net) {
    var queue = new PriorityQueue<EscapeHints.Search>(Comparator.comparingDouble(EscapeHints.Search::length));
    queue.add(new EscapeHints.Search(pin, 0, List.of(pin)));
    Set<Integer> seen = new HashSet<>();
    while (!queue.isEmpty() && seen.size() < 128) {
      var state = queue.poll();
      if (!seen.add(state.item().get_id_no())) continue;
      if (state.item() instanceof Via) return state.path();
      if (!(state.item() instanceof Connectable connected)) continue;
      for (Item item : connected.get_normal_contacts()) {
        if (!item.contains_net(net) || seen.contains(item.get_id_no())
            || item instanceof Pin || item instanceof ConductionArea) continue;
        double length = state.length() + (item instanceof Trace t ? TargetedRoute.lengthMm(board, t) : 0);
        if (length > 5.0) continue;
        List<Item> path = new ArrayList<>(state.path()); path.add(item);
        queue.add(new EscapeHints.Search(item, length, path));
      }
    }
    throw new IllegalStateException("No alternate pin-to-via escape <=5mm");
  }
  static boolean removable(Item item, RoutingBoard board) {
    if (!(item instanceof Trace || item instanceof Via)) return false;
    if (item.get_fixed_state() == FixedState.SYSTEM_FIXED || item.get_fixed_state() == FixedState.USER_FIXED) return false;
    for (int i = 0; i < item.net_count(); i++) {
      String group = board.rules.nets.get(item.get_net_no(i)).get_class().get_name();
      if (group.equals("rf_fixed") || group.equals("usb_fixed")) return false;
    }
    return true;
  }
  public static void main(String[] args) throws Exception {
    if (args.length != 7 && args.length != 8) throw new IllegalArgumentException(
      "Usage: AnchoredEscape CURRENT.core.frb ALT.frb NEW.ses ORIGINAL.dsn REFERENCE PIN TOTAL_SECONDS [native-vbt]");
    boolean nativeVbt = args.length == 8 && Set.of("native-vbt", "native-vbt-10", "native-vbt-20").contains(args[7]);
    boolean directTxLed = args.length == 8 && args[7].equals("direct-txled");
    boolean rightTxLed = args.length == 8 && args[7].equals("right-txled");
    boolean shortTxLed = args.length == 8 && (args[7].equals("short-txled") || rightTxLed);
    boolean explicit = nativeVbt || directTxLed || shortTxLed;
    if (args.length == 8 && !explicit) throw new IllegalArgumentException("Unknown explicit anchor");
    int seconds = Integer.parseInt(args[6]);
    if (seconds < 1 || seconds > 180) throw new IllegalArgumentException("Budget exceeds180seconds");
    Path output = Paths.get(args[2]).toAbsolutePath();
    if (Files.exists(output) || Files.exists(Paths.get(output + ".state.frb"))) throw new IOException("New output paths required");
    var original = TargetedRoute.read(Files.readAllBytes(Paths.get(args[0])));
    var alternate = explicit ? null : TargetedRoute.read(Files.readAllBytes(Paths.get(args[1])));
    var current = TargetedRoute.read(TargetedRoute.serialize(original));
    RoutingBoard board = current.board();
    Pin pin = EscapeHints.pin(board, args[4], args[5]);
    String name = board.rules.nets.get(pin.get_net_no(0)).name;
    if (!TargetedRoute.thinLogic(board.rules.nets.get(pin.get_net_no(0)))) throw new IOException("Logic only");
    int net = pin.get_net_no(0);
    List<Item> hint = List.of();
    if (!explicit) {
      Pin altPin = EscapeHints.pin(alternate.board(), args[4], args[5]);
      Net altNet = alternate.board().rules.nets.get(name, 1);
      if (altNet == null || !altPin.contains_net(altNet.net_number)) throw new IOException("Alternate pin/net mismatch");
      if (pin.get_center().to_float().distance(altPin.get_center().to_float()) > 1.1)
        throw new IOException("Pin placements differ");
      hint = escape(alternate.board(), altPin, altNet.net_number);
    } else if (!args[4].equals("U10") || !(nativeVbt && args[5].equals("10") && name.equals("V_BT")
        || (directTxLed || shortTxLed) && args[5].equals("15") && name.equals("TX_LED")))
      throw new IOException("Explicit anchor does not match selected pin/net");
    int initialViolations = TargetedRoute.violations(board);
    Map<Integer, Integer> initialCounts = TargetedRoute.counts(board);
    int initialScore = TargetedRoute.nonGroundScore(board, initialCounts);
    Set<Integer> anchors = new HashSet<>();
    int halfWidth = (int) Math.round(board.communication.coordinate_transform.dsn_to_board(75));
    int clearance = board.rules.nets.get(net).get_class().get_trace_clearance_class();
    if (explicit) {
      var transform = board.communication.coordinate_transform;
      double pinX = directTxLed || shortTxLed ? 171.9375 : 170.3225, pinY = directTxLed || shortTxLed ? 118.7275 : 117.1125;
      var start = transform.dsn_to_board(new double[]{pinX * 1000, -pinY * 1000}).round();
      double viaX = rightTxLed ? 172.9375 : shortTxLed ? 171.0375 : directTxLed ? pinX : args[7].equals("native-vbt-20") ? 170.9425 : args[7].equals("native-vbt-10") ? 170.9325 : 170.9225;
      double viaY = shortTxLed ? 120.0275 : directTxLed ? 119.3475 : pinY;
      var end = transform.dsn_to_board(new double[]{viaX * 1000, -viaY * 1000}).round();
      if (pin.get_center().to_float().distance(start.to_float()) > 1.1) throw new IOException("Native anchor pin mismatch");
      var explicitPath = shortTxLed ? new app.freerouting.geometry.planar.Polyline(new app.freerouting.geometry.planar.Point[]{
        start, transform.dsn_to_board(new double[]{171937.5,-119077.5}).round(),
        transform.dsn_to_board(rightTxLed ? new double[]{172887.5,-120027.5} : new double[]{171037.5,-119977.5}).round(),end})
        : new app.freerouting.geometry.planar.Polyline(start,end);
      var added = board.insert_trace_without_cleaning(explicitPath,
        0, halfWidth, new int[]{net}, clearance, FixedState.SYSTEM_FIXED);
      if (added == null) throw new IOException("Explicit stub insert failed");
      anchors.add(added.get_id_no());
      var stack = board.library.padstacks.get("Via[0-3]_600:300_um");
      if (stack == null) throw new IOException("Missing identical600/300via stack");
      var addedVia = board.insert_via(stack, end, new int[]{net}, clearance, FixedState.SYSTEM_FIXED, !shortTxLed);
      if (addedVia == null) throw new IOException("Explicit local via insert failed");
      anchors.add(addedVia.get_id_no());
      System.out.println(TargetedRoute.JSON.toJson(Map.of("explicitAnchor", args[4]+"."+args[5]+" "+name,
        "nativeValidationRequired", directTxLed || shortTxLed,
        "viaMm", List.of(viaX, viaY), "diameterMm", 0.6, "drillMm", 0.3,
        "attachAllowedOnlyThisVia", !shortTxLed, "requiresNativeFilledCappedStamp", !shortTxLed)));
    }
    for (Item item : hint) {
      if (item instanceof PolylineTrace trace) {
        var added = board.insert_trace_without_cleaning(trace.polyline(), trace.get_layer(), halfWidth,
          new int[]{net}, clearance, FixedState.SYSTEM_FIXED);
        if (added == null) throw new IOException("Anchor trace insert failed");
        anchors.add(added.get_id_no());
      } else if (item instanceof Via via) {
        var stack = board.library.padstacks.get(via.get_padstack().name);
        if (stack == null) throw new IOException("Missing identical via padstack");
        var added = board.insert_via(stack, via.get_center(), new int[]{net}, clearance,
          FixedState.SYSTEM_FIXED, via.attach_allowed);
        if (added == null) throw new IOException("Anchor via insert failed");
        anchors.add(added.get_id_no());
      }
    }
    Map<Integer, String> removed = new LinkedHashMap<>();
    for (int iteration = 0; iteration < 20; iteration++) {
      Set<Item> collisions = new HashSet<>();
      for (var violation : new ClearanceViolations(board.get_items()).list) {
        boolean first = anchors.contains(violation.first_item.get_id_no());
        boolean second = anchors.contains(violation.second_item.get_id_no());
        if (!first && !second) continue;
        Item other = first ? violation.second_item : violation.first_item;
        if (anchors.contains(other.get_id_no())) continue;
        if (!removable(other, board)) {
          System.out.println(TargetedRoute.JSON.toJson(Map.of("blockedAnchor", first ? violation.first_item.get_id_no() : violation.second_item.get_id_no(),
            "blockedBy", other.get_id_no(), "otherType", other.getClass().getSimpleName(), "layer", violation.layer,
            "expectedCore", violation.expected_clearance, "actualCore", violation.actual_clearance,
            "otherNet", other.net_count() == 1 ? board.rules.nets.get(other.get_net_no(0)).name : "multiple")));
          throw new IOException("Anchor clashes with protected object" + other.get_id_no());
        }
        collisions.add(other);
      }
      if (collisions.isEmpty()) break;
      if (removed.size() + collisions.size() > 32) throw new IOException("Too many displaced objects");
      for (Item item : collisions) {
        String netName = item.net_count() == 1 ? board.rules.nets.get(item.get_net_no(0)).name : "multiple";
        removed.put(item.get_id_no(), netName); board.remove_item(item);
      }
    }
    if (TargetedRoute.violations(board) > initialViolations) throw new IOException("Anchor clearance regression");
    Map<Integer, String> fixed = GroundFanout.protectedItems(board);
    fixed.entrySet().removeIf(e -> board.get_item(e.getKey()).get_fixed_state() == FixedState.SHOVE_FIXED);
    List<GroundFanout.Piece> fixedTraces = GroundFanout.tracePieces(board, true).stream()
      .filter(p -> board.get_item(p.id()).get_fixed_state() != FixedState.SHOVE_FIXED).toList();
    List<String> placements = GroundFanout.placements(board);
    System.out.println(TargetedRoute.JSON.toJson(Map.of("anchorNet", name, "anchorObjects", anchors,
      "removedSoftObjects", removed, "initialNonGround", initialScore,
      "afterAnchorMissing", TargetedRoute.missingNonGround(board, TargetedRoute.counts(board)))));
    TargetedRoute.Budget budget = new TargetedRoute.Budget(seconds);
    TargetedRoute.variedCosts = true;
    byte[] working = TargetedRoute.serialize(current), accepted = null;
    int acceptedScore = initialScore;
    for (int pass = 0; pass < 12 && !budget.is_stop_requested(); pass++) {
      current = TargetedRoute.read(working);
      List<String> names = new ArrayList<>(TargetedRoute.missingNonGround(current.board(), TargetedRoute.counts(current.board())).keySet());
      names.remove(name); names.add(0, name);
      if ((pass & 1) == 1) Collections.reverse(names);
      for (String queued : names) {
        current = TargetedRoute.read(working);
        Net queuedNet = current.board().rules.nets.get(queued, 1);
        var countsBefore = TargetedRoute.counts(current.board());
        if (countsBefore.get(queuedNet.net_number) == 0) continue;
        List<Pin> pins = new ArrayList<>(queuedNet.get_pins());
        pins.sort(Comparator.comparingInt(p -> p.get_connected_set(queuedNet.net_number).size()));
        Set<String> tried = new HashSet<>();
        for (Pin oldPin : pins) {
          if (budget.is_stop_requested()) break;
          var attempt = TargetedRoute.read(working);
          Pin active = (Pin) attempt.board().get_item(oldPin.get_id_no());
          String connected = active.get_connected_set(queuedNet.net_number).stream().map(Item::get_id_no).sorted().toList().toString();
          if (!tried.add(connected)) continue;
          if (TargetedRoute.power(queued) && active.first_layer() == active.last_layer()) {
            try { TargetedRoute.fanoutBounded(attempt, active, budget, 3000, true); }
            catch (Exception rejectedNeck) {
              System.out.println(TargetedRoute.JSON.toJson(Map.of("pass", pass + 1, "net", queued,
                "rejectedPowerNeck", String.valueOf(rejectedNeck.getMessage()))));
              continue;
            }
          }
          int[] widths = TargetedRoute.thinLogic(queuedNet) ? TargetedRoute.setWidth(attempt, queuedNet.net_number, 150) : null;
          AutorouteEngine.AutorouteResult result;
          try { result = TargetedRoute.route(attempt, active, budget, 3000, pass + 2); }
          finally { if (widths != null) TargetedRoute.restoreWidth(attempt, queuedNet.net_number, widths); }
          var countsAfter = TargetedRoute.counts(attempt.board());
          boolean useful = countsAfter.get(queuedNet.net_number) < countsBefore.get(queuedNet.net_number)
            && TargetedRoute.violations(attempt.board()) <= initialViolations
            && TargetedRoute.preserved(attempt.board(), fixed, fixedTraces, placements);
          System.out.println(TargetedRoute.JSON.toJson(Map.of("pass", pass + 1, "net", queued,
            "route", result.toString(), "acceptedStep", useful,
            "before", countsBefore.get(queuedNet.net_number), "after", countsAfter.get(queuedNet.net_number))));
          if (useful) { working = TargetedRoute.serialize(attempt); break; }
        }
      }
      current = TargetedRoute.read(working);
      var counts = TargetedRoute.counts(current.board());
      int score = TargetedRoute.nonGroundScore(current.board(), counts);
      if (score < acceptedScore && TargetedRoute.criticalRestored(current.board(), initialCounts, counts)) {
        accepted = working; acceptedScore = score;
      }
      System.out.println(TargetedRoute.JSON.toJson(Map.of("passComplete", pass + 1,
        "nonGroundMissing", score, "best", acceptedScore,
        "queuedMissingNets", TargetedRoute.missingNonGround(current.board(), counts))));
      if (acceptedScore == 0) break;
    }
    if (accepted != null) {
      current = TargetedRoute.read(accepted);
      try (OutputStream out = Files.newOutputStream(output, StandardOpenOption.CREATE_NEW)) {
        if (!SpecctraSesFileWriter.write(current.board(), out, Paths.get(args[3]).getFileName().toString()))
          throw new IOException("SES writer failed");
      }
      Files.write(Paths.get(output + ".state.frb"), accepted, StandardOpenOption.CREATE_NEW);
      Files.writeString(Paths.get(output + ".thin-traces.json"), TargetedRoute.JSON.toJson(TargetedRoute.thinTraces(current.board())), StandardOpenOption.CREATE_NEW);
    } else {
      // Explicitly marked branch for reserving multiple legal pin escapes before
      // restoring displaced soft nets. Never exported as a native-import SES.
      Files.write(Paths.get(output + ".EXPLORATORY.state.frb"), working, StandardOpenOption.CREATE_NEW);
      var branch = TargetedRoute.read(working);
      Files.writeString(Paths.get(output + ".EXPLORATORY-missing.json"),
        TargetedRoute.JSON.toJson(TargetedRoute.missingNonGround(branch.board(), TargetedRoute.counts(branch.board()))),
        StandardOpenOption.CREATE_NEW);
    }
    System.out.println(TargetedRoute.JSON.toJson(Map.of("summary", true, "improved", accepted != null,
      "beforeNonGround", initialScore, "afterNonGround", acceptedScore,
      "remaining", accepted == null ? TargetedRoute.missingNonGround(original.board(), initialCounts)
        : TargetedRoute.missingNonGround(current.board(), TargetedRoute.counts(current.board())))));
  }
}
