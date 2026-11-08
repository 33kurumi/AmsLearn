package com.dongchen.campus.config;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.env.ConfigurableEnvironment;

/**
 * 启动前检查 H2 文件数据库是否可写。
 *
 * <p>背景：本机（Windows + DSH 沙箱 + H2 2.3.232）中，被沙箱创建的文件对后续新进程表现为
 * {@code Files.isWritable(...) == false}（文件实际可写，但 java.nio 的可写性探测返回 false）。
 * H2 通过 {@code FilePathDisk.canWrite()}（内部即 {@code Files.isWritable}）判断数据库文件，
 * 于是「已存在的数据库文件」会被 H2 以只读方式打开，导致所有写库接口报
 * {@code The database is read only ... [90097-232]}。</p>
 *
 * <p>处理方式：启动时先用一个极小的写探测表验证数据库可写；若判定为只读，把旧库文件改名备份
 * （{@code data/student-project.mv.db.readonly.bak}）后继续启动，让 ddl-auto 与 seeder 重新建库
 * 并导入演示数据，保证服务可用。该监听器只挂载在 {@link com.dongchen.campus.CampusServiceApplication#main}
 * 上，不影响测试（测试使用内存库）。</p>
 */
public class ReadOnlyDatabaseRepairListener implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    private static final Logger log = LoggerFactory.getLogger(ReadOnlyDatabaseRepairListener.class);

    private static final String H2_FILE_PREFIX = "jdbc:h2:file:";

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        ConfigurableEnvironment env = event.getEnvironment();
        String url = env.getProperty("spring.datasource.url", "");
        if (!url.startsWith(H2_FILE_PREFIX)) {
            return;
        }
        Path dbFile = resolveDatabaseFile(url);
        if (dbFile == null) {
            return;
        }
        if (!Files.exists(dbFile)) {
            // H2 的 MVStore 文件名为 <url 路径>.mv.db（旧版本为 .h2.db），探测时需按实际文件判断存在性。
            Path mvFile = Paths.get(dbFile.toString() + ".mv.db");
            Path h2File = Paths.get(dbFile.toString() + ".h2.db");
            if (Files.exists(mvFile)) {
                dbFile = mvFile;
            } else if (Files.exists(h2File)) {
                dbFile = h2File;
            } else {
                return;
            }
        }
        String username = env.getProperty("spring.datasource.username", "sa");
        String password = env.getProperty("spring.datasource.password", "");
        try (Connection connection = DriverManager.getConnection(url, username, password)) {
            try (Statement statement = connection.createStatement()) {
                statement.execute("CREATE TABLE IF NOT EXISTS write_probe (id INT)");
                statement.execute("DELETE FROM write_probe");
                statement.execute("DROP TABLE IF EXISTS write_probe");
            }
            log.info("H2 文件数据库可写：{}", dbFile);
        } catch (SQLException e) {
            String message = e.getMessage() == null ? "" : e.getMessage();
            if (!message.contains("read only")) {
                log.warn("H2 文件数据库启动探测失败（继续启动，交由 Spring 处理）：{}", message);
                return;
            }
            backupAndRemove(dbFile);
        }
    }

    private Path resolveDatabaseFile(String url) {
        String path = url.substring(H2_FILE_PREFIX.length());
        int optionIndex = path.indexOf(';');
        if (optionIndex >= 0) {
            path = path.substring(0, optionIndex);
        }
        if (path.isEmpty()) {
            return null;
        }
        return Paths.get(path).toAbsolutePath().normalize();
    }

    private void backupAndRemove(Path dbFile) {
        Path backup = dbFile.resolveSibling(dbFile.getFileName() + ".readonly.bak");
        try {
            Files.move(dbFile, backup, StandardCopyOption.REPLACE_EXISTING);
            log.warn("检测到 H2 数据库文件为只读（沙箱文件可写性探测限制），已备份为 {}，将重建数据库并重新导入演示数据。", backup);
        } catch (IOException e) {
            log.error("无法处理只读的 H2 数据库文件 {}：{}", dbFile, e.getMessage());
        }
    }
}
