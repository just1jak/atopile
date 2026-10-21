import app.freerouting.board.*;
import app.freerouting.geometry.planar.*;
import java.nio.file.*;
import java.util.*;

/** Bounded in-memory search; all native geometry and source state remain untouched. */
public class AnchorSearch {
  static Point point(RoutingBoard b,double x,double y) {return b.communication.coordinate_transform.dsn_to_board(new double[]{x*1000,-y*1000}).round();}
  public static void main(String[] args) throws Exception {
    if(args.length!=4) throw new IllegalArgumentException("Usage: AnchorSearch CORE.frb REFERENCE PIN NEW.json");
    if(!args[1].equals("U10")||!Set.of("15","16").contains(args[2]))throw new IllegalArgumentException("Only U10.15/16 bottom-side escape search is defined");
    Path output=Paths.get(args[3]);if(Files.exists(output))throw new IllegalArgumentException("New output required");
    var state=TargetedRoute.read(Files.readAllBytes(Paths.get(args[0])));var b=state.board();
    Pin pin=EscapeHints.pin(b,args[1],args[2]);int net=pin.get_net_no(0);
    var stack=b.library.padstacks.get("Via[0-3]_600:300_um");
    var source=ExportAnchoredSes.xy(b,pin.get_center());double px=source.get(0),py=source.get(1);
    int width=(int)Math.round(b.communication.coordinate_transform.dsn_to_board(75));
    int clearance=b.rules.nets.get(net).get_class().get_trace_clearance_class();
    List<Map<String,Object>> candidates=new ArrayList<>();int tested=0;
    boolean pci=args[2].equals("16");
    for(int yi=12;yi<=(pci?70:100);yi++)for(int xi=(pci?0:-30);xi<=(pci?60:30);xi++) {
      double vx=px+xi*.05,vy=py+yi*.05;
      Via via=b.insert_via(stack,point(b,vx,vy),new int[]{net},clearance,FixedState.SYSTEM_FIXED,true);
      if(via==null)continue;
      boolean viaHard=false;
      for(var v:via.clearance_violations()){
        Item other=v.first_item==via?v.second_item:v.first_item;
        if(!AnchoredEscape.removable(other,b))viaHard=true;
      }
      if(viaHard){b.remove_item(via);continue;}
      for(double straight: new double[]{.35,.5,.65,.8}) {
        double dx=vx-px,dy=vy-py-straight;if(dy<0)continue;
        List<Point> pts=new ArrayList<>();pts.add(pin.get_center());pts.add(point(b,px,py+straight));
        if(Math.abs(dx)>0.000001&&dy>0.000001){
          if(dy>=Math.abs(dx))pts.add(point(b,vx,py+straight+Math.abs(dx)));
          else pts.add(point(b,px+Math.signum(dx)*dy,vy));
        }
        pts.add(point(b,vx,vy));
        Polyline path=new Polyline(pts.toArray(Point[]::new));
        PolylineTrace trace=b.insert_trace_without_cleaning(path,0,width,new int[]{net},clearance,FixedState.SYSTEM_FIXED);
        if(trace==null)continue;tested++;
        Map<Integer,String> victims=new TreeMap<>();boolean hard=false;
        for(Item added:List.of(trace,via))for(var v:added.clearance_violations()){
          Item other=v.first_item==added?v.second_item:v.first_item;
          if(other==trace||other==via)continue;
          if(!AnchoredEscape.removable(other,b)){hard=true;break;}
          victims.put(other.get_id_no(),other.net_count()==1?b.rules.nets.get(other.get_net_no(0)).name:"multiple");
        }
        if(!hard){
          double length=TargetedRoute.lengthMm(b,trace);
          long powerVictims=victims.values().stream().filter(TargetedRoute::power).count();
          Map<String,Object> c=new LinkedHashMap<>();c.put("reference",args[1]);c.put("pin",args[2]);c.put("net",b.rules.nets.get(net).name);
          c.put("pointsMm",Arrays.stream(path.corner_arr()).map(p->ExportAnchoredSes.xy(b,p)).toList());
          c.put("viaMm",List.of(vx,vy));c.put("widthMm",.15);c.put("diameterMm",.6);c.put("drillMm",.3);
          c.put("attachAllowed",true);c.put("requiresNativeValidation",true);c.put("victims",victims);
          c.put("lengthMm",length);c.put("score",powerVictims*100+victims.size()*2+length);candidates.add(c);
        }
        b.remove_item(trace);
      }
      b.remove_item(via);
    }
    candidates.sort(Comparator.comparingDouble(c->((Number)c.get("score")).doubleValue()));
    List<Map<String,Object>> diverse=new ArrayList<>();Set<String> signatures=new HashSet<>();
    for(var c:candidates){
      @SuppressWarnings("unchecked") var victims=(Map<Integer,String>)c.get("victims");
      String signature=new TreeSet<>(victims.values()).toString();
      if(signatures.add(signature))diverse.add(c);
    }
    var result=Map.of("testedPaths",tested,"legalPaths",candidates.size(),"candidates",candidates.stream().limit(30).toList(),"diverseCandidates",diverse);
    Files.writeString(output,TargetedRoute.JSON.toJson(result),StandardOpenOption.CREATE_NEW);
    System.out.println(TargetedRoute.JSON.toJson(result));
  }
}
