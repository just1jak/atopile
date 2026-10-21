import app.freerouting.autoroute.*;
import app.freerouting.board.*;
import app.freerouting.designforms.specctra.SpecctraSesFileWriter;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Bounded pass-level search with balanced victim accounting and immutable best state. */
public class RepairSearch {
  public static void main(String[] args)throws Exception {
    if(args.length!=5)throw new IllegalArgumentException("Usage: RepairSearch CORE.frb NEW.ses ORIGINAL.dsn SECONDS RANDOM_SEED");
    Path out=Paths.get(args[1]);if(Files.exists(out)||Files.exists(Paths.get(out+".state.frb")))throw new IOException("New output required");
    int seconds=Integer.parseInt(args[3]);if(seconds<1||seconds>240)throw new IllegalArgumentException("Budget exceeds240seconds");
    var random=new Random(Long.parseLong(args[4]));
    byte[] source=Files.readAllBytes(Paths.get(args[0]));var initial=TargetedRoute.read(source);var initialCounts=TargetedRoute.counts(initial.board());
    var fixed=GroundFanout.protectedItems(initial.board());fixed.entrySet().removeIf(e->initial.board().get_item(e.getKey()).get_fixed_state()==FixedState.SHOVE_FIXED);
    var traces=GroundFanout.tracePieces(initial.board(),true).stream().filter(p->initial.board().get_item(p.id()).get_fixed_state()!=FixedState.SHOVE_FIXED).toList();
    var placements=GroundFanout.placements(initial.board());int maxViolations=TargetedRoute.violations(initial.board());
    int initialScore=TargetedRoute.nonGroundScore(initial.board(),initialCounts),bestScore=initialScore,attempts=0;
    byte[] working=source,best=null;var budget=new TargetedRoute.Budget(seconds);TargetedRoute.variedCosts=true;
    System.out.println(TargetedRoute.JSON.toJson(Map.of("initial",TargetedRoute.missingNonGround(initial.board(),initialCounts),"maxEngineViolations",maxViolations)));
    for(int pass=0;pass<60&&!budget.is_stop_requested()&&bestScore>0;pass++) {
      var snapshot=TargetedRoute.read(working);var names=new ArrayList<>(TargetedRoute.missingNonGround(snapshot.board(),TargetedRoute.counts(snapshot.board())).keySet());
      Collections.shuffle(names,random);
      for(String name:names) {
        if(budget.is_stop_requested())break;
        var state=TargetedRoute.read(working);var net=state.board().rules.nets.get(name,1);var before=TargetedRoute.counts(state.board());
        if(before.get(net.net_number)==0)continue;
        var pins=new ArrayList<Pin>(net.get_pins());Collections.shuffle(pins,random);Set<String> tried=new HashSet<>();
        for(Pin old:pins){
          if(budget.is_stop_requested())break;
          var candidate=TargetedRoute.read(working);Pin pin=(Pin)candidate.board().get_item(old.get_id_no());
          String set=pin.get_connected_set(net.net_number).stream().map(Item::get_id_no).sorted().toList().toString();if(!tried.add(set))continue;
          try {
            if(TargetedRoute.power(name)&&pin.first_layer()==pin.last_layer())TargetedRoute.fanoutBounded(candidate,pin,budget,2000,true);
            int[] widths=TargetedRoute.thinLogic(net)?TargetedRoute.setWidth(candidate,net.net_number,150):null;
            AutorouteEngine.AutorouteResult result;
            try{result=TargetedRoute.route(candidate,pin,budget,2500,2+random.nextInt(12));}
            finally{if(widths!=null)TargetedRoute.restoreWidth(candidate,net.net_number,widths);}
            var after=TargetedRoute.counts(candidate.board());int score=TargetedRoute.nonGroundScore(candidate.board(),after);attempts++;
            boolean accept=after.get(net.net_number)<before.get(net.net_number)&&score<=Math.max(8,initialScore+3)
              &&TargetedRoute.criticalRestored(candidate.board(),initialCounts,after)
              &&TargetedRoute.violations(candidate.board())<=maxViolations
              &&TargetedRoute.preserved(candidate.board(),fixed,traces,placements);
            System.out.println(TargetedRoute.JSON.toJson(Map.of("pass",pass+1,"net",name,"reference",candidate.board().components.get(pin.get_component_no()).name,
              "pin",pin.name(),"result",result,"accepted",accept,"total",score,"missing",TargetedRoute.missingNonGround(candidate.board(),after))));
            if(accept){
              working=TargetedRoute.serialize(candidate);
              if(score<bestScore){bestScore=score;best=working;Files.write(Paths.get(out+".best.state.frb"),best);
                System.out.println(TargetedRoute.JSON.toJson(Map.of("newBest",score,"missing",TargetedRoute.missingNonGround(candidate.board(),after))));}
              break;
            }
          }catch(IOException rejection){System.out.println(TargetedRoute.JSON.toJson(Map.of("rejected",String.valueOf(rejection.getMessage()),"net",name)));}
        }
        if(bestScore==0)break;
      }
      if((pass%8)==7&&best!=null)working=best;
    }
    if(best!=null){var accepted=TargetedRoute.read(best);
      try(var stream=Files.newOutputStream(out,StandardOpenOption.CREATE_NEW)){if(!SpecctraSesFileWriter.write(accepted.board(),stream,Paths.get(args[2]).getFileName().toString()))throw new IOException("SES export failed");}
      Files.write(Paths.get(out+".state.frb"),best,StandardOpenOption.CREATE_NEW);
      Files.writeString(Paths.get(out+".thin-traces.json"),TargetedRoute.JSON.toJson(TargetedRoute.thinTraces(accepted.board())),StandardOpenOption.CREATE_NEW);
    }
    var finalState=TargetedRoute.read(best==null?source:best);
    System.out.println(TargetedRoute.JSON.toJson(Map.of("summary",true,"initial",initialScore,"best",bestScore,"attempts",attempts,
      "missing",TargetedRoute.missingNonGround(finalState.board(),TargetedRoute.counts(finalState.board())),"protectedGeometryPreserved",true)));
  }
}
