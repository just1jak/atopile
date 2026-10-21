import app.freerouting.board.*;
import app.freerouting.designforms.specctra.DsnFile;
import app.freerouting.interactive.*;
import app.freerouting.logger.FRLogger;
import java.io.FileInputStream;
import java.util.Locale;

/** Read-only per-net DSN import accounting, with no router or save calls. */
public class LoadDsnNetCounts {
    public static void main(String[] args) throws Exception {
        FRLogger.disableLogging();
        BoardHandlingHeadless handler = new BoardHandlingHeadless(Locale.ENGLISH, false, 0.01f);
        try (FileInputStream input = new FileInputStream(args[0])) {
            var result = DsnFile.read(input, handler, new BoardObserverAdaptor(),
                new ItemIdNoGenerator(), TestLevel.RELEASE_VERSION);
            if (result != DsnFile.ReadResult.OK) throw new IllegalStateException(result.toString());
        }
        RoutingBoard b = handler.get_routing_board();
        if (b.components.count() != 263 || b.rules.nets.max_net_no() != 194)
            throw new IllegalStateException("Incomplete import");
        RatsNest nest = new RatsNest(b, Locale.ENGLISH);
        int nonGround = 0;
        for (int n = 1; n <= b.rules.nets.max_net_no(); n++) {
            int count = nest.incomplete_count(n);
            if (count == 0) continue;
            String name = b.rules.nets.get(n).name;
            if (!name.equals("GND")) nonGround += count;
            System.out.printf("%s %d%n", name, count);
        }
        System.out.printf("total=%d nonGround=%d warnings=%d errors=%d%n",
            nest.incomplete_count(), nonGround, FRLogger.getLogEntries().getWarningCount(),
            FRLogger.getLogEntries().getErrorCount());
        if (args.length > 1) for (var line : nest.get_airlines()) {
            if (!line.net.name.equals(args[1])) continue;
            System.out.printf("airline net=%s from=%d/%s/%s to=%d/%s/%s lengthCore=%s%n",
                line.net.name, line.from_item.get_id_no(), line.from_item.getClass().getSimpleName(),
                line.from_corner, line.to_item.get_id_no(), line.to_item.getClass().getSimpleName(),
                line.to_corner, line.from_corner.distance(line.to_corner));
            for (Item item : new Item[]{line.from_item, line.to_item}) {
                if (item instanceof Pin pin) System.out.println("pin=" + b.components.get(pin.get_component_no()).name + "." + pin.name());
                if (item instanceof PolylineTrace trace) System.out.println("trace=" + java.util.Arrays.toString(trace.polyline().corner_arr()));
            }
        }
    }
}
