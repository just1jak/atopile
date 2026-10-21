import app.freerouting.board.*;
import app.freerouting.designforms.specctra.SpecctraSesFileWriter;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Export-only clone includes added pin anchors; never unlocks original seed copper. */
public class ExportAnchoredSes {
  static List<Double> xy(RoutingBoard board, app.freerouting.geometry.planar.Point point) {
    double[] p = board.communication.coordinate_transform.board_to_dsn(point.to_float());
    return List.of(p[0]/1000, -p[1]/1000);
  }
  public static void main(String[] args) throws Exception {
    if (args.length != 4) throw new IllegalArgumentException("Usage: ExportAnchoredSes PRE_ANCHOR_BASE.core.frb CURRENT.core.frb NEW.ses ORIGINAL.dsn");
    Path target = Paths.get(args[2]).toAbsolutePath(), manifest = Paths.get(target+".anchors.json");
    if (Files.exists(target) || Files.exists(manifest)) throw new IOException("New output paths required");
    byte[] baseBytes = Files.readAllBytes(Paths.get(args[0])), currentBytes = Files.readAllBytes(Paths.get(args[1]));
    var base = TargetedRoute.read(baseBytes);
    var current = TargetedRoute.read(currentBytes);
    var baseItems = GroundFanout.protectedItems(base.board());
    var baseTraces = GroundFanout.tracePieces(base.board(), true).stream()
      .filter(p -> base.board().get_item(p.id()).get_fixed_state() != FixedState.SHOVE_FIXED).toList();
    List<Map<String,Object>> anchors = new ArrayList<>();
    Set<Integer> unlocked = new TreeSet<>();
    for (Item item : current.board().get_items()) {
      if (item.get_fixed_state() != FixedState.SYSTEM_FIXED && item.get_fixed_state() != FixedState.USER_FIXED) continue;
      Map<String,Object> anchor = new LinkedHashMap<>();
      anchor.put("fixedId",item.get_id_no());
      anchor.put("fixedState",item.get_fixed_state().toString());
      if (item.net_count()!=1) continue;
      String net = current.board().rules.nets.get(item.get_net_no(0)).name;
      anchor.put("net",net);
      if (item instanceof PolylineTrace trace) {
        var pieces = GroundFanout.tracePieces(current.board(), false).stream().filter(p -> p.id()==item.get_id_no()).toList();
        if (pieces.stream().allMatch(p -> GroundFanout.covered(p,baseTraces))) continue;
        anchor.put("kind","track");anchor.put("layerIndex",trace.get_layer());
        anchor.put("canonicalLayer",List.of("F.Cu","In1.Cu","In2.Cu","B.Cu").get(trace.get_layer()));
        anchor.put("widthMm",TargetedRoute.widthUm(current.board(),trace)/1000);
        anchor.put("pointsMm",Arrays.stream(trace.polyline().corner_arr()).map(p -> xy(current.board(),p)).toList());
      } else if (item instanceof Via via) {
        if (baseItems.containsKey(item.get_id_no())) continue;
        if (!via.get_padstack().name.equals("Via[0-3]_600:300_um")) throw new IOException("Unexpected added via stack");
        anchor.put("kind","via");anchor.put("positionMm",xy(current.board(),via.get_center()));
        anchor.put("diameterMm",0.6);anchor.put("drillMm",0.3);
        anchor.put("layers",List.of("F.Cu","B.Cu"));anchor.put("attachAllowed",via.attach_allowed);
        anchor.put("requiresFilledCappedBothSidesTented",via.attach_allowed);
      } else continue;
      anchors.add(anchor);unlocked.add(item.get_id_no());
    }
    for (int id : unlocked) current.board().get_item(id).set_fixed_state(FixedState.UNFIXED);
    if (!TargetedRoute.preserved(current.board(),baseItems,baseTraces,GroundFanout.placements(base.board())))
      throw new IOException("Original seed guard failed on export-only clone");
    try (OutputStream out = Files.newOutputStream(target,StandardOpenOption.CREATE_NEW)) {
      if (!SpecctraSesFileWriter.write(current.board(),out,Paths.get(args[3]).getFileName().toString()))
        throw new IOException("SES writer failed");
    }
    var report = Map.of("baseSha256",CheckpointToSes.sha(baseBytes),"sourceSha256",CheckpointToSes.sha(currentBytes),
      "originalFixedCopperPreserved",true,"routingStateUnchanged",true,"exportCloneUnlockedOnly",unlocked,"anchors",anchors);
    Files.writeString(manifest,TargetedRoute.JSON.toJson(report),StandardOpenOption.CREATE_NEW);
    System.out.println(TargetedRoute.JSON.toJson(report));
  }
}
