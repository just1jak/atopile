import app.freerouting.board.*;
import app.freerouting.interactive.*;
import app.freerouting.rules.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Read only the immutable copied checkpoint, printing plane/readiness information. */
public class InspectGround {
  public static void main(String[] args) throws Exception {
    RoutingBoard board;
    Settings settings;
    try (ObjectInputStream in = new ObjectInputStream(Files.newInputStream(Paths.get(args[0])))) {
      board = (RoutingBoard) in.readObject();
      settings = (Settings) in.readObject();
    }
    board.set_test_level(TestLevel.RELEASE_VERSION);
    if (args.length > 1) {
      Item item = board.get_item(Integer.parseInt(args[1]));
      System.out.printf("inspect_item=%d class=%s state=%s layers=%d..%d comp=%d clearance=%d%n",
        item.get_id_no(), item.getClass().getName(), item.get_fixed_state(), item.first_layer(),
        item.last_layer(), item.get_component_no(), item.clearance_class_no());
    }
    Net ground = board.rules.nets.get("GND", 1);
    if (ground == null) throw new IllegalStateException("No GND net");
    System.out.printf("GND number=%d contains_plane=%s class=%s ignored=%s pins=%d airwires=%d%n",
      ground.net_number, ground.contains_plane(), ground.get_class().get_name(),
      ground.get_class().is_ignored_by_autorouter, ground.get_pins().size(),
      new RatsNest(board, Locale.ENGLISH).incomplete_count(ground.net_number));
    System.out.printf("fanout=%s autoroute=%s postroute=%s vias=%s planeViaCosts=%d viaCosts=%d pass=%d%n",
      settings.autoroute_settings.get_with_fanout(), settings.autoroute_settings.get_with_autoroute(),
      settings.autoroute_settings.get_with_postroute(), settings.autoroute_settings.get_vias_allowed(),
      settings.autoroute_settings.get_plane_via_costs(), settings.autoroute_settings.get_via_costs(),
      settings.autoroute_settings.get_start_pass_no());
    for (int i = 0; i < board.get_layer_count(); i++)
      System.out.printf("layer=%d %s signal=%s settingsActive=%s classActive=%s%n", i,
        board.layer_structure.arr[i].name, board.layer_structure.arr[i].is_signal,
        settings.autoroute_settings.get_layer_active(i), ground.get_class().is_active_routing_layer(i));
    for (ConductionArea area : board.get_conduction_areas())
      System.out.printf("area layer=%s net=%d fixed=%s contacts=%d connected=%d obstacle=%s foreignViaDrillable=%s foreignTraceObstacle=%s%n",
        board.layer_structure.arr[area.get_layer()].name, area.get_net_no(0), area.get_fixed_state(),
        area.get_normal_contacts().size(), area.get_connected_set(ground.net_number).size(),
        area.get_is_obstacle(), area.is_drillable(2), area.is_trace_obstacle(2));
    int planeConnected = 0, onlyPin = 0;
    for (Pin pin : ground.get_pins()) {
      Set<Item> connected = pin.get_connected_set(ground.net_number);
      if (connected.stream().anyMatch(x -> x instanceof ConductionArea)) planeConnected++;
      if (connected.size() == 1) onlyPin++;
    }
    System.out.printf("GND pins connected_to_plane=%d isolated_pin=%d%n", planeConnected, onlyPin);
  }
}
