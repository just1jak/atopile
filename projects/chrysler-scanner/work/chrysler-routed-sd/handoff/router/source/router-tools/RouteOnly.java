import app.freerouting.autoroute.*;
import app.freerouting.board.*;
import app.freerouting.designforms.specctra.SpecctraSesFileWriter;
import java.nio.file.*;
import java.io.*;
import java.util.*;

/** Routes one net with every other trace/via temporarily frozen in memory. */
public class RouteOnly {
  static FixedState exportState(List<GroundFanout.Piece> pieces,List<GroundFanout.Piece> original,
      Map<Integer,FixedState> states,boolean victimPass)throws IOException {
    Set<FixedState> matched=new HashSet<>();boolean protectedOverlap=false;
    for(var piece:pieces)for(var old:original) {
      if(GroundFanout.covered(piece,List.of(old)))matched.add(states.get(old.id()));
      if(states.get(old.id())!=FixedState.UNFIXED&&piece.key().equals(old.key())
          &&piece.lo().side_of(old.lo(),old.hi())==app.freerouting.geometry.planar.Side.COLLINEAR
          &&piece.hi().side_of(old.lo(),old.hi())==app.freerouting.geometry.planar.Side.COLLINEAR
          &&piece.hi().compare_x_y(old.lo())>0&&piece.lo().compare_x_y(old.hi())<0)protectedOverlap=true;
    }
    boolean entirelyOriginal=pieces.stream().allMatch(p->GroundFanout.covered(p,original));
    if(!entirelyOriginal&&protectedOverlap)throw new IOException("New trace extends or combines protected copper");
    if(matched.isEmpty()&&victimPass&&!protectedOverlap)return FixedState.UNFIXED;
    if(matched.size()==1&&(entirelyOriginal||matched.contains(FixedState.UNFIXED)))return matched.iterator().next();
    throw new IOException("Ambiguous original fixed state after subdivision");
  }
  public static void main(String[] args)throws Exception {
    if(args.length!=5&&args.length!=6)throw new IllegalArgumentException("Usage: RouteOnly CORE.frb NET NEW.ses ORIGINAL.dsn SECONDS [victim-pass]");
    boolean victimPass=args.length==6&&args[5].equals("victim-pass");
    boolean preserveTarget=Boolean.getBoolean("atopile.route.preserveTargetCopper");
    String name=args[1];Path out=Paths.get(args[2]);if(Files.exists(out))throw new IOException("New output required");
    int seconds=Integer.parseInt(args[4]);if(seconds<1||seconds>120)throw new IllegalArgumentException("Maximum120seconds");
    byte[] source=Files.readAllBytes(Paths.get(args[0]));var original=TargetedRoute.read(source);var board=original.board();
    var net=board.rules.nets.get(name,1);if(net==null||!TargetedRoute.thinLogic(net))throw new IOException("Reviewed logic net required");
    var initialCounts=TargetedRoute.counts(board);int initialViolations=TargetedRoute.violations(board);
    Map<Integer,FixedState> originalStates=new HashMap<>();
    for(Item item:board.get_items()) {originalStates.put(item.get_id_no(),item.get_fixed_state());
      if(!victimPass&&(item instanceof Trace||item instanceof Via)&&!item.contains_net(net.net_number))item.set_fixed_state(FixedState.SYSTEM_FIXED);}
    if(preserveTarget)for(Item item:board.get_items())if((item instanceof Trace||item instanceof Via)&&item.contains_net(net.net_number))item.set_fixed_state(FixedState.SYSTEM_FIXED);
    var fixed=GroundFanout.protectedItems(board);var fixedTraces=GroundFanout.tracePieces(board,true);var placements=GroundFanout.placements(board);
    var sourcePieces=GroundFanout.tracePieces(board,false);byte[] frozen=TargetedRoute.serialize(original),best=null;
    int bestCount=initialCounts.get(net.net_number);var budget=new TargetedRoute.Budget(seconds);TargetedRoute.variedCosts=true;
    System.out.println(TargetedRoute.JSON.toJson(Map.of("target",name,"before",bestCount,"allMissing",TargetedRoute.missingNonGround(board,initialCounts),"otherCopperFrozen",!victimPass)));
    for(int pass=0;pass<12&&!budget.is_stop_requested()&&bestCount>0;pass++) {
      var start=TargetedRoute.read(frozen);var pins=new ArrayList<Pin>(start.board().rules.nets.get(name,1).get_pins());
      if(pass%2==1)Collections.reverse(pins);Set<String> tried=new HashSet<>();
      for(Pin old:pins) {
        if(budget.is_stop_requested())break;var attempt=TargetedRoute.read(frozen);Pin pin=(Pin)attempt.board().get_item(old.get_id_no());
        String set=pin.get_connected_set(net.net_number).stream().map(Item::get_id_no).sorted().toList().toString();if(!tried.add(set))continue;
        int[] widths=TargetedRoute.setWidth(attempt,net.net_number,150);AutorouteEngine.AutorouteResult result;
        try{result=TargetedRoute.route(attempt,pin,budget,3500,pass+2);}finally{TargetedRoute.restoreWidth(attempt,net.net_number,widths);}
        var counts=TargetedRoute.counts(attempt.board());
        if(victimPass&&counts.get(net.net_number)<bestCount) {
          for(Item item:attempt.board().get_items())if((item instanceof Trace||item instanceof Via)&&item.contains_net(net.net_number))item.set_fixed_state(FixedState.SYSTEM_FIXED);
          for(int round=0;round<12&&!budget.is_stop_requested();round++) {
            List<Integer> victims=new ArrayList<>();for(var c:initialCounts.entrySet())
              if(c.getKey()!=net.net_number&&counts.get(c.getKey())>c.getValue())victims.add(c.getKey());
            if(victims.isEmpty())break;if((round+pass)%2==1)Collections.reverse(victims);
            boolean changed=false;
            for(int victim:victims) {
              var vn=attempt.board().rules.nets.get(victim);var vp=new ArrayList<Pin>(vn.get_pins());if(round%2==1)Collections.reverse(vp);
              Set<String> triedVictims=new HashSet<>();
              for(Pin oldVictim:vp) {
                if(budget.is_stop_requested())break;var repair=TargetedRoute.read(TargetedRoute.serialize(attempt));Pin active=(Pin)repair.board().get_item(oldVictim.get_id_no());
                String connected=active.get_connected_set(victim).stream().map(Item::get_id_no).sorted().toList().toString();if(!triedVictims.add(connected))continue;
                if(TargetedRoute.power(vn.name)&&active.first_layer()==active.last_layer())try{TargetedRoute.fanoutBounded(repair,active,budget,1500,true);}catch(IOException rejected){continue;}
                int[] rw=TargetedRoute.thinLogic(vn)?TargetedRoute.setWidth(repair,victim,150):null;AutorouteEngine.AutorouteResult rr;
                try{rr=TargetedRoute.route(repair,active,budget,1800,round+pass+2);}finally{if(rw!=null)TargetedRoute.restoreWidth(repair,victim,rw);}
                var rc=TargetedRoute.counts(repair.board());boolean take=rc.get(victim)<counts.get(victim)&&rc.get(net.net_number)==0
                  &&TargetedRoute.violations(repair.board())<=initialViolations&&TargetedRoute.preserved(repair.board(),fixed,fixedTraces,placements);
                System.out.println(TargetedRoute.JSON.toJson(Map.of("victim",vn.name,"round",round+1,"result",rr,"accepted",take,"allMissing",TargetedRoute.missingNonGround(repair.board(),rc))));
                if(take){attempt=repair;counts=rc;changed=true;break;}
              }
            }
            if(!changed)break;
          }
        }
        boolean otherCounts=true;
        for(var c:initialCounts.entrySet())if(c.getKey()!=net.net_number&&!Objects.equals(counts.get(c.getKey()),c.getValue()))otherCounts=false;
        boolean accepted=counts.get(net.net_number)<bestCount&&otherCounts&&TargetedRoute.violations(attempt.board())<=initialViolations
          &&TargetedRoute.preserved(attempt.board(),fixed,fixedTraces,placements);
        System.out.println(TargetedRoute.JSON.toJson(Map.of("pass",pass+1,"pin",attempt.board().components.get(pin.get_component_no()).name+"."+pin.name(),
          "result",result,"accepted",accepted,"missing",counts.get(net.net_number),"otherNetCountsUnchanged",otherCounts)));
        if(accepted){best=TargetedRoute.serialize(attempt);bestCount=counts.get(net.net_number);break;}
      }
    }
    if(best!=null){var accepted=TargetedRoute.read(best);var b=accepted.board();
      for(Item item:b.get_items()) {
        if(originalStates.containsKey(item.get_id_no()))item.set_fixed_state(originalStates.get(item.get_id_no()));
        else if(item instanceof Trace trace&&!item.contains_net(net.net_number)) {
          var pieces=GroundFanout.tracePieces(b,false).stream().filter(p->p.id()==item.get_id_no()).toList();
          item.set_fixed_state(exportState(pieces,sourcePieces,originalStates,victimPass));
        }else if(victimPass&&(item instanceof Trace||item instanceof Via))item.set_fixed_state(FixedState.UNFIXED);
        else if(!item.contains_net(net.net_number))throw new IOException("Unexpected added non-target object");
        else item.set_fixed_state(FixedState.UNFIXED);
      }
      var originalBoard=TargetedRoute.read(source).board();
      if(!TargetedRoute.preserved(b,GroundFanout.protectedItems(originalBoard),GroundFanout.tracePieces(originalBoard,true),placements))
        throw new IOException("Restored original seed guard failed");
      List<Map<String,Object>> copper=new ArrayList<>();
      for(Item item:b.get_items())if(item.contains_net(net.net_number)) {
        if(item instanceof PolylineTrace t)copper.add(Map.of("kind","track","id",t.get_id_no(),"net",name,"layerIndex",t.get_layer(),
          "widthMm",TargetedRoute.widthUm(b,t)/1000,"pointsMm",Arrays.stream(t.polyline().corner_arr()).map(p->ExportAnchoredSes.xy(b,p)).toList(),"fixed",t.get_fixed_state().toString()));
        if(item instanceof Via v){if(!v.get_padstack().name.equals("Via[0-3]_600:300_um"))throw new IOException("Unexpected target via");
          copper.add(Map.of("kind","via","id",v.get_id_no(),"net",name,"positionMm",ExportAnchoredSes.xy(b,v.get_center()),"diameterMm",.6,"drillMm",.3,"attachAllowed",v.attach_allowed,"fixed",v.get_fixed_state().toString()));}
      }
      try(var stream=Files.newOutputStream(out,StandardOpenOption.CREATE_NEW)){if(!SpecctraSesFileWriter.write(b,stream,Paths.get(args[3]).getFileName().toString()))throw new IOException("SES export failed");}
      Files.write(Paths.get(out+".state.frb"),TargetedRoute.serialize(accepted),StandardOpenOption.CREATE_NEW);
      Files.writeString(Paths.get(out+".target-copper.json"),TargetedRoute.JSON.toJson(Map.of("sourceCoreSha256",CheckpointToSes.sha(source),"target",name,
        "beforeMissing",initialCounts.get(net.net_number),"afterMissing",bestCount,"allOtherCopperTemporarilyFrozen",!victimPass,"originalFixedStatesRestoredForExport",true,"copper",copper)),StandardOpenOption.CREATE_NEW);
    }
    System.out.println(TargetedRoute.JSON.toJson(Map.of("summary",true,"target",name,"before",initialCounts.get(net.net_number),"after",bestCount,"improved",best!=null)));
  }
}
