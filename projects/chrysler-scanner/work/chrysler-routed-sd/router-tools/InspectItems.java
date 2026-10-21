import app.freerouting.board.*;
import java.nio.file.*;
import java.util.*;

/** Read-only inspection of exact core objects. */
public class InspectItems {
  public static void main(String[] args) throws Exception {
    var state = TargetedRoute.read(Files.readAllBytes(Paths.get(args[0])));
    var board = state.board();
    List<Integer> ids=new ArrayList<>();
    for(int i=1;i<args.length;i++) {
      if(args[i].startsWith("net:")) {var net=board.rules.nets.get(args[i].substring(4),1);for(Item item:board.get_items())if(item.contains_net(net.net_number))ids.add(item.get_id_no());}
      else ids.add(Integer.parseInt(args[i]));
    }
    for (int id : ids) {
      Item item = board.get_item(id);
      Map<String,Object> out = new LinkedHashMap<>();
      out.put("id", id);
      if (item == null) { out.put("missing", true); }
      else {
        out.put("type", item.getClass().getSimpleName());
        out.put("fixed", item.get_fixed_state().toString());
        List<String> nets = new ArrayList<>();
        for (int n=0;n<item.net_count();n++) nets.add(board.rules.nets.get(item.get_net_no(n)).name);
        out.put("nets", nets);
        if (item instanceof Trace t) {
          out.put("layer", t.get_layer());
          out.put("halfWidthCore", t.get_half_width());
          out.put("firstCore", t.first_corner().toString());
          out.put("lastCore", t.last_corner().toString());
          if (t instanceof PolylineTrace p) out.put("pointsMm", Arrays.stream(p.polyline().corner_arr()).map(pt -> ExportAnchoredSes.xy(board,pt)).toList());
        }
        if (item instanceof Via v) {out.put("positionMm",ExportAnchoredSes.xy(board,v.get_center()));out.put("attachAllowed",v.attach_allowed);}
        if (item instanceof Pin p) {out.put("pin",p.name());out.put("reference",board.components.get(p.get_component_no()).name);out.put("positionMm",ExportAnchoredSes.xy(board,p.get_center()));}
        if (item instanceof ConductionArea c) {out.put("layer",c.get_layer());out.put("area",c.get_area().toString());}
      }
      System.out.println(TargetedRoute.JSON.toJson(out));
    }
  }
}
