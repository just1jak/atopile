import app.freerouting.board.BoardObserverAdaptor;
import app.freerouting.board.ItemIdNoGenerator;
import app.freerouting.board.RoutingBoard;
import app.freerouting.board.TestLevel;
import app.freerouting.designforms.specctra.DsnFile;
import app.freerouting.interactive.BoardHandlingHeadless;
import app.freerouting.interactive.RatsNest;
import app.freerouting.logger.FRLogger;
import java.io.FileInputStream;
import java.util.Locale;

/** Read-only DSN import proof. Does not route, export, or save the input. */
public class LoadDsnOnly {
    public static void main(String[] args) throws Exception {
        FRLogger.disableLogging();
        FRLogger.getLogEntries().clear();
        BoardHandlingHeadless handler = new BoardHandlingHeadless(Locale.ENGLISH, false, 0.01f);
        try (FileInputStream input = new FileInputStream(args[0])) {
            DsnFile.ReadResult result = DsnFile.read(input, handler, new BoardObserverAdaptor(),
                new ItemIdNoGenerator(), TestLevel.RELEASE_VERSION);
            if (result != DsnFile.ReadResult.OK) throw new IllegalStateException(result.toString());
        }
        RoutingBoard board = handler.get_routing_board();
        System.out.printf("import_warnings=%d import_errors=%d%n",
            FRLogger.getLogEntries().getWarningCount(), FRLogger.getLogEntries().getErrorCount());
        System.out.println(FRLogger.getLogEntries().getAsString());
        System.out.printf("{\"import_result\":\"OK\",\"components\":%d,\"nets\":%d,\"layers\":%d,"
            + "\"pins\":%d,\"traces\":%d,\"vias\":%d,\"airwires\":%d}%n",
            board.components.count(), board.rules.nets.max_net_no(), board.get_layer_count(),
            board.get_pins().size(), board.get_traces().size(), board.get_vias().size(),
            new RatsNest(board, Locale.ENGLISH).incomplete_count());
        for (int i = 0; i < board.get_layer_count(); i++)
            System.out.printf("layer %d name=%s signal=%s active=%s%n", i,
                board.layer_structure.arr[i].name, board.layer_structure.arr[i].is_signal,
                handler.get_settings().autoroute_settings.get_layer_active(i));
        System.out.printf("default_width_um=%s automatic_neckdown=%s%n",
            2 * board.communication.coordinate_transform.board_to_dsn(board.rules.get_default_trace_half_width(0)),
            handler.get_settings().get_automatic_neckdown());
        for (int i = 1; i < board.rules.clearance_matrix.get_class_count(); i++)
            System.out.printf("clearance_class=%s same_class_clearance_um=%s%n",
                board.rules.clearance_matrix.get_name(i),
                board.communication.coordinate_transform.board_to_dsn(board.rules.clearance_matrix.get_value(i, i, 0, false)));
        double smallestNeckdownUm = Double.POSITIVE_INFINITY;
        for (app.freerouting.board.Pin pin : board.get_pins()) {
            for (int layer = 0; layer < board.get_layer_count(); layer++) {
                if (pin.is_on_layer(layer) && board.layer_structure.arr[layer].is_signal)
                    smallestNeckdownUm = Math.min(smallestNeckdownUm,
                        2 * board.communication.coordinate_transform.board_to_dsn(pin.get_trace_neckdown_halfwidth(layer)));
            }
        }
        System.out.printf("smallest_pin_neckdown_um=%s%n", smallestNeckdownUm);
        for (int i = 0; i < board.rules.net_classes.count(); i++) {
            app.freerouting.rules.NetClass rules = board.rules.net_classes.get(i);
            System.out.printf("route_class=%s width_um=%s front=%s back=%s%n", rules.get_name(),
                2 * board.communication.coordinate_transform.board_to_dsn(rules.get_trace_half_width(0)),
                rules.is_active_routing_layer(0), rules.is_active_routing_layer(board.get_layer_count() - 1));
        }
        for (app.freerouting.board.Item item : board.get_items()) {
            if (item instanceof app.freerouting.board.ObstacleArea && item.get_component_no() == 0) {
                app.freerouting.board.ObstacleArea area = (app.freerouting.board.ObstacleArea) item;
                System.out.printf("global_obstacle=%s layer=%s bounds=%s%n", item.getClass().getSimpleName(),
                    board.layer_structure.arr[area.get_layer()].name, area.bounding_box());
            }
        }
    }
}
