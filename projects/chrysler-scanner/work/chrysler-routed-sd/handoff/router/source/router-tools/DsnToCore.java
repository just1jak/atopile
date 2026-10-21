import app.freerouting.board.*;
import app.freerouting.designforms.specctra.DsnFile;
import app.freerouting.interactive.*;
import app.freerouting.logger.FRLogger;
import java.nio.file.*;
import java.io.*;
import java.util.*;

/** Pure headless DSN parser and local core serialization; native files are never changed. */
public class DsnToCore {
  public static void main(String[] args)throws Exception {
    if(args.length!=2)throw new IllegalArgumentException("Usage: DsnToCore INPUT.dsn NEW.core.frb");
    Path input=Paths.get(args[0]),output=Paths.get(args[1]);if(Files.exists(output))throw new IOException("New output required");
    byte[] original=Files.readAllBytes(input);FRLogger.disableLogging();FRLogger.getLogEntries().clear();
    BoardHandlingHeadless handler=new BoardHandlingHeadless(Locale.ENGLISH,false,.01f);
    var result=DsnFile.read(new ByteArrayInputStream(original),handler,new BoardObserverAdaptor(),new ItemIdNoGenerator(),TestLevel.RELEASE_VERSION);
    if(result!=DsnFile.ReadResult.OK||FRLogger.getLogEntries().getWarningCount()!=0||FRLogger.getLogEntries().getErrorCount()!=0)
      throw new IOException("DSN import must be clean: "+result+" "+FRLogger.getLogEntries().getAsString());
    if(!Arrays.equals(original,Files.readAllBytes(input)))throw new IOException("Input changed during parse");
    var board=handler.get_routing_board();
    // KiCad exports unlocked copper as (type route); FR1.9 reads that as
    // USER_FIXED. Native locked copper is (type fix), read as SYSTEM_FIXED.
    // Normalize only the former for this native-derived input, never its locks.
    int nativeUnlockedCopper=0;
    for(Item item:board.get_items())if((item instanceof Trace||item instanceof Via)&&item.get_fixed_state()==FixedState.USER_FIXED){
      item.set_fixed_state(FixedState.UNFIXED);nativeUnlockedCopper++;
    }
    boolean initializedCosts=false;
    for(int i=0;i<board.get_layer_count();i++) {
      var costs=handler.get_settings().autoroute_settings;
      if(costs.get_horizontal_trace_costs(i)<=0||costs.get_vertical_trace_costs(i)<=0) {
        costs.set_preferred_direction_trace_costs(i,1);
        costs.set_against_preferred_direction_trace_costs(i,2.5);
        initializedCosts=true;
      }
    }
    if(handler.get_settings().autoroute_settings.get_via_costs()<=0){handler.get_settings().autoroute_settings.set_via_costs(50);initializedCosts=true;}
    if(handler.get_settings().autoroute_settings.get_plane_via_costs()<=0)handler.get_settings().autoroute_settings.set_plane_via_costs(5);
    var state=new TargetedRoute.State(board,handler.get_settings());
    Files.write(output,TargetedRoute.serialize(state),StandardOpenOption.CREATE_NEW);
    System.out.println(TargetedRoute.JSON.toJson(Map.of("sourceSha256",CheckpointToSes.sha(original),"components",board.components.count(),"pins",board.get_pins().size(),
      "missing",TargetedRoute.missingNonGround(board,TargetedRoute.counts(board)),"engineViolations",TargetedRoute.violations(board),"nativeFilesUnchanged",true,"initializedPositiveSearchCosts",initializedCosts,"nativeUnlockedCopperNormalized",nativeUnlockedCopper)));
  }
}
