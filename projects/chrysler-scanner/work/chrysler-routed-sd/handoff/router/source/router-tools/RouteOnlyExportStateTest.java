import app.freerouting.board.FixedState;
import app.freerouting.geometry.planar.Point;
import java.io.IOException;
import java.util.*;

/** Pure geometry/export-state checks; no boards, routing or filesystem changes. */
public class RouteOnlyExportStateTest {
  static GroundFanout.Piece piece(int id,int lo,int hi){return new GroundFanout.Piece(id,"F:logic:150",Point.get_instance(lo,0),Point.get_instance(hi,0));}
  static void check(boolean value){if(!value)throw new AssertionError();}
  static void reject(List<GroundFanout.Piece> wanted,List<GroundFanout.Piece> old,Map<Integer,FixedState> states,boolean victim)throws Exception{
    try{RouteOnly.exportState(wanted,old,states,victim);throw new AssertionError("Expected refusal");}catch(IOException expected){}
  }
  public static void main(String[] args)throws Exception{
    var old=List.of(piece(1,0,100));var protectedState=Map.of(1,FixedState.SYSTEM_FIXED);var ordinary=Map.of(1,FixedState.UNFIXED);
    check(RouteOnly.exportState(List.of(piece(2,200,300)),old,ordinary,true)==FixedState.UNFIXED);
    reject(List.of(piece(2,200,300)),old,ordinary,false);
    check(RouteOnly.exportState(List.of(piece(2,10,90)),old,protectedState,true)==FixedState.SYSTEM_FIXED);
    check(RouteOnly.exportState(List.of(piece(2,10,90)),old,ordinary,true)==FixedState.UNFIXED);
    check(RouteOnly.exportState(List.of(piece(2,0,150)),old,ordinary,true)==FixedState.UNFIXED);
    reject(List.of(piece(2,0,150)),old,protectedState,true);
    reject(List.of(piece(3,0,50),piece(3,50,100)),List.of(piece(1,0,50),piece(2,50,100)),Map.of(1,FixedState.SYSTEM_FIXED,2,FixedState.UNFIXED),true);
    check(RouteOnly.exportState(List.of(piece(2,100,150)),old,protectedState,true)==FixedState.UNFIXED);
    System.out.println("8 export-state tests passed; new victims allowed, protected extensions refused");
  }
}
