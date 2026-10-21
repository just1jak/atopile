import app.freerouting.board.RoutingBoard;
import app.freerouting.board.TestLevel;
import app.freerouting.designforms.specctra.SpecctraSesFileWriter;
import app.freerouting.interactive.RatsNest;
import app.freerouting.interactive.Settings;
import app.freerouting.logger.FRLogger;
import java.io.*;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.*;

/** Export a trusted, locally generated FreeRouting 1.9 GUI checkpoint without routing.
 * Does not modify the source checkpoint, DSN, native PCB, or running engine.
 * SES still contains placement: sanitize it before native KiCad import.
 */
public final class CheckpointToSes {
    private static final String JAR_SHA = "9084a4888937a7f31f857ecc12aa7a37407f51160e4d2892dff9c9bb47ae3102";
    private static final long MAX_BYTES = 128L * 1024 * 1024;

    static String sha(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    static byte[] stableCopy(Path source, Path copy) throws Exception {
        BasicFileAttributes before = Files.readAttributes(source, BasicFileAttributes.class);
        if (!before.isRegularFile() || before.size() <= 0 || before.size() > MAX_BYTES)
            throw new IOException("Checkpoint must be a nonempty regular file <=128 MiB");
        byte[] bytes = Files.readAllBytes(source);
        BasicFileAttributes after = Files.readAttributes(source, BasicFileAttributes.class);
        if (before.size() != after.size() || !before.lastModifiedTime().equals(after.lastModifiedTime())
                || !Objects.equals(before.fileKey(), after.fileKey())
                || !Arrays.equals(bytes, Files.readAllBytes(source)))
            throw new IOException("Checkpoint changed while copying; retry later");
        Files.write(copy, bytes, StandardOpenOption.CREATE_NEW);
        return bytes;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException(
            "Usage: CheckpointToSes TRUSTED_LOCAL.frb NEW_OUTPUT.ses ORIGINAL_INPUT.dsn");
        Path jar = Paths.get(RoutingBoard.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        if (!sha(Files.readAllBytes(jar)).equals(JAR_SHA))
            throw new IOException("Requires the verified FreeRouting 1.9.0 JAR");
        Path source = Paths.get(args[0]).toRealPath();
        Path output = Paths.get(args[1]).toAbsolutePath();
        Path dsn = Paths.get(args[2]).toRealPath();
        Path copy = Paths.get(output + ".frb");
        if (Files.exists(output) || Files.exists(copy))
            throw new IOException("Output or immutable checkpoint copy already exists");
        byte[] bytes = stableCopy(source, copy);
        // No MainApplication/analytics client is initialized in this core-only process.
        FRLogger.disableLogging();
        RoutingBoard board;
        int objects = 0;
        try (ObjectInputStream in = new ObjectInputStream(new ByteArrayInputStream(bytes))) {
            // Only consume trusted task-local engine output; never deserialize downloaded FRBs.
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                "maxdepth=256;maxrefs=3000000;maxbytes=134217728;maxarray=3000000;*"));
            Object first = in.readObject(); objects++;
            if (!(first instanceof RoutingBoard)) throw new IOException("First FRB object is not RoutingBoard");
            board = (RoutingBoard) first;
            Object settings = in.readObject(); objects++;
            if (!(settings instanceof Settings)) throw new IOException("Second FRB object is not Settings");
            if (!(in.readObject() instanceof app.freerouting.board.CoordinateTransform))
                throw new IOException("Missing coordinate transform");
            objects++;
            if (!(in.readObject() instanceof app.freerouting.boardgraphics.GraphicsContext))
                throw new IOException("Missing graphics state");
            objects++;
            if (!(in.readObject() instanceof java.awt.Point)
                    || !(in.readObject() instanceof java.awt.Point)
                    || !(in.readObject() instanceof java.awt.Rectangle))
                throw new IOException("Missing GUI checkpoint state");
            objects += 3;
            // Validate any remaining serialized window state too; never load GUI objects into windows.
            try { while (true) { in.readObject(); objects++; } }
            catch (EOFException complete) { /* Object stream has no explicit end marker. */ }
        }
        board.set_test_level(TestLevel.RELEASE_VERSION);
        int airwires = new RatsNest(board, Locale.ENGLISH).incomplete_count();
        Path temporary = Files.createTempFile(output.getParent(), ".checkpoint-ses-", ".tmp");
        try {
            try (OutputStream out = Files.newOutputStream(temporary)) {
                if (!SpecctraSesFileWriter.write(board, out, dsn.getFileName().toString()))
                    throw new IOException("SES writer failed");
            }
            // No replacement: each checkpoint/candidate has a distinct immutable output name.
            Files.move(temporary, output);
        } finally { Files.deleteIfExists(temporary); }
        System.out.printf(Locale.ROOT,
            "{\"checkpointSha256\":\"%s\",\"checkpointBytes\":%d,\"serializedObjects\":%d,"
            + "\"components\":%d,\"nets\":%d,\"pins\":%d,\"traces\":%d,\"vias\":%d,"
            + "\"engineAirwires\":%d,\"sesBytes\":%d}%n",
            sha(bytes), bytes.length, objects, board.components.count(), board.rules.nets.max_net_no(),
            board.get_pins().size(), board.get_traces().size(), board.get_vias().size(),
            airwires, Files.size(output));
    }
}
