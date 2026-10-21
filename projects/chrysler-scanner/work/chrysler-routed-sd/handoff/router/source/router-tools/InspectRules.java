import app.freerouting.autoroute.*;
import java.nio.file.*;
public class InspectRules {
  public static void main(String[] args)throws Exception {
    var s=TargetedRoute.read(Files.readAllBytes(Paths.get(args[0])));var n=s.board().rules.nets.get(args[1],1);
    var c=new AutorouteControl(s.board(),n.net_number,s.settings(),50,s.settings().autoroute_settings.get_trace_cost_arr());
    System.out.println("class="+n.get_class().get_name()+" viaAllowed="+c.vias_allowed+" attachAllowed="+c.attach_smd_allowed);
    for(int i=0;i<c.layer_active.length;i++)System.out.println("layer="+i+" active="+c.layer_active[i]+" horizontalCost="+c.trace_costs[i].horizontal+" verticalCost="+c.trace_costs[i].vertical);
  }
}
