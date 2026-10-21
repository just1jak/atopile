import app.freerouting.board.RoutingBoard;
import app.freerouting.board.TestLevel;
import app.freerouting.interactive.RatsNest;
import app.freerouting.interactive.Settings;
import app.freerouting.logger.FRLogger;
import app.freerouting.rules.Net;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Read-only statistics from a stable copy of our trusted local routing checkpoint. */
public final class CheckpointStats {
    static String quote(String text) {
        return "\"" + text.replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("TRUSTED_LOCAL.frb NEW_COPY.frb NEW_REPORT.json");
        Path jar = Paths.get(RoutingBoard.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        if (!CheckpointToSes.sha(Files.readAllBytes(jar)).equals(
            "9084a4888937a7f31f857ecc12aa7a37407f51160e4d2892dff9c9bb47ae3102"))
            throw new IOException("Requires the verified FreeRouting1.9.0 JAR");
        Path source=Paths.get(args[0]).toRealPath(), copy=Paths.get(args[1]).toAbsolutePath(), report=Paths.get(args[2]).toAbsolutePath();
        if (Files.exists(copy) || Files.exists(report)) throw new IOException("Outputs must be new paths");
        byte[] bytes=CheckpointToSes.stableCopy(source,copy);
        FRLogger.disableLogging();
        RoutingBoard board;
        Settings settings;
        try (ObjectInputStream in=new ObjectInputStream(new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                "maxdepth=256;maxrefs=3000000;maxbytes=134217728;maxarray=3000000;*"));
            Object first=in.readObject(), second=in.readObject();
            if (!(first instanceof RoutingBoard) || !(second instanceof Settings))
                throw new IOException("Not a local FreeRouting board/settings checkpoint");
            board=(RoutingBoard)first; settings=(Settings)second;
        }
        board.set_test_level(TestLevel.RELEASE_VERSION);
        RatsNest nest=new RatsNest(board,Locale.ENGLISH);
        int total=nest.incomplete_count(), ground=0, sum=0;
        List<String> perNet=new ArrayList<>();
        for (int i=1;i<=board.rules.nets.max_net_no();i++) {
            Net net=board.rules.nets.get(i);
            if (net==null) continue;
            int count=nest.incomplete_count(i); sum+=count;
            if (net.name.equals("GND")) ground+=count;
            if (count>0) perNet.add(String.format(Locale.ROOT,
                "{\"number\":%d,\"name\":%s,\"incomplete\":%d,\"containsPlane\":%s,\"class\":%s,\"ignored\":%s}",
                i,quote(net.name),count,net.contains_plane(),quote(net.get_class().get_name()),net.get_class().is_ignored_by_autorouter));
        }
        String json=String.format(Locale.ROOT,
            "{\"checkpoint\":%s,\"stableCopy\":%s,\"checkpointSha256\":%s,\"checkpointBytes\":%d,"
            +"\"sourceUnmodifiedByHelper\":true,\"enginePassSetting\":%d,\"engineAirwires\":%d,\"sumPerNetAirwires\":%d,"
            +"\"groundAirwires\":%d,\"nonGroundAirwires\":%d,\"components\":%d,\"traces\":%d,\"vias\":%d,\"perNet\":[%s]}\n",
            quote(source.toString()),quote(copy.toString()),quote(CheckpointToSes.sha(bytes)),bytes.length,
            settings.autoroute_settings.get_start_pass_no(),total,sum,ground,total-ground,
            board.components.count(),board.get_traces().size(),board.get_vias().size(),String.join(",",perNet));
        Files.writeString(report,json,StandardOpenOption.CREATE_NEW);
        System.out.print(json);
    }
}
