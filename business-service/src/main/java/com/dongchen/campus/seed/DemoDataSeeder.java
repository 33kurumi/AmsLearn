package com.dongchen.campus.seed;

import com.dongchen.campus.common.JsonHelper;
import com.dongchen.campus.common.Maps;
import com.dongchen.campus.config.AppProperties;
import com.dongchen.campus.domain.*;
import com.dongchen.campus.repository.*;
import com.dongchen.campus.security.PasswordHasher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * 演示数据种子：班级、师生账号、班级配置、掌握度、交互记录、错题与报告。
 * 仅在 app.demo-data=true 且 user_info 为空时执行。
 */
@Component
@Order(2)
public class DemoDataSeeder implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(DemoDataSeeder.class);
    private static final String DEMO_PASSWORD = "123456";

    private static final String BOUNDARY_RULES =
            "仅解答高等数学（考研数学一/二/三）范围内内容；不提供作业与考试的最终答案；不讨论无关话题。";

    private static final String[][] QA_TEMPLATES = {
            {"这道题为什么不能用洛必达？lim_{x→0}(sin x - x)/x^3 我用两次洛必达算出来和答案不一样",
                    "**先判断未定式类型**：$x\\to 0$ 时 $\\sin x - x \\sim -\\frac{x^3}{6}$，分母是 $x^3$，属于 $0/0$ 型，洛必达本身可用。\n\n你结果不同多半是求导时漏了链式法则：\n1. 第一次求导：$(\\cos x - 1)/(3x^2)$；\n2. 第二次：$-\\sin x/(6x)$；\n3. 第三次：$-\\cos x/6 \\to -1/6$。\n\n**更快的做法**是直接用泰勒展开：$\\sin x = x - x^3/6 + o(x^3)$，一步得到 $-1/6$。"},
            {"老师，等价无穷小替换在加减法里什么时候可以用？",
                    "等价无穷小替换在**乘除**中始终可用；在**加减**中要看替换后是否出现主项抵消。\n\n判断方法：把两项都展开到同一阶，若低阶项抵消、只剩高阶项，则不能只替换低阶等价无穷小。\n\n例如 $\\sin x - \\tan x$：$\\sin x \\sim x$、$\\tan x \\sim x$ 直接替换得 0，是错的；实际 $\\sin x - \\tan x \\sim -x^3/2$。"},
            {"求不定积分 ∫x·ln x dx，分部积分怎么选 u 和 dv？",
                    "用 **LIATE 原则**（对数、反三角优先作 $u$）：\n\n令 $u = \\ln x$，$dv = x\\,dx$，则 $du = dx/x$，$v = x^2/2$。\n\n$$\\int x\\ln x\\,dx = \\frac{x^2}{2}\\ln x - \\frac{1}{2}\\int x\\,dx = \\frac{x^2}{2}\\ln x - \\frac{x^2}{4} + C$$\n\n选错的典型是把 $\\ln x$ 放进 $dv$，会越积越复杂。"},
            {"定积分换元后上下限怎么确定？我这题算出来是负的",
                    "换元 $x = \\varphi(t)$ 时，**上下限要同步换成 $t$ 的取值**，并且保持“下限对应下限、上限对应上限”。\n\n若 $\\varphi$ 单调递减，可以交换上下限再补一个负号。算出来为负通常是：\n- 忘了换限，仍用 $x$ 的端点；\n- 或者 $dx = \\varphi'(t)dt$ 中漏了 $\\varphi'(t)$ 的符号。"},
            {"级数 ∑(1/n) 发散但 ∑(1/n²) 收敛，怎么快速判断收敛性？",
                    "记住 **p 级数**：$\\sum 1/n^p$ 在 $p>1$ 收敛、$p\\le 1$ 发散。\n\n快速判断顺序：\n1. 通项是否趋于 0（不趋于 0 必发散）；\n2. 与 p 级数/几何级数比较（极限比较法）；\n3. 含 $n$ 的幂或阶乘用比值法、根值法；\n4. 交错级数用莱布尼茨判别法。"},
            {"多元函数极值里 AC-B²=0 的情况怎么处理？",
                    "$AC-B^2=0$ 时二阶判别法**失效**，需要回到定义：\n\n1. 在驻点附近沿不同路径考察 $f$ 的增量符号；\n2. 或把函数配方，观察是否为 $\\pm(x-a)^2$、$\\pm(x-a)^4$ 等定号形式；\n3. 若沿某方向增、另一方向减，则不是极值。\n\n考试中这类点通常会设计成可配方的形式。"},
            {"这个二重积分交换积分次序的积分区域怎么画？",
                    "步骤：\n1. 由原积分限写出区域不等式（如 $0\\le y\\le 1$，$y\\le x\\le 1$）；\n2. 在坐标系中画出边界曲线，找出交点；\n3. 按新的先 $y$ 后 $x$（或反之）重新描述：固定 $x$，看 $y$ 从哪条曲线到哪条曲线；\n4. 必要时把区域拆成两块分别写限。"},
            {"微分方程 y' + y = e^x 的通解怎么求？",
                    "一阶线性方程 $y' + P(x)y = Q(x)$，用积分因子：\n\n$$\\mu(x) = e^{\\int P dx} = e^x$$\n\n两边乘 $e^x$：$(e^xy)' = e^{2x}$，积分得 $e^xy = \\frac{1}{2}e^{2x} + C$，\n\n所以 $y = \\frac{1}{2}e^x + Ce^{-x}$。"},
            {"拉格朗日中值定理证明题怎么构造辅助函数？",
                    "构造辅助函数的核心是**把要证的等式整理成“某个函数的导数为 0”**。\n\n常用套路：\n- 出现 $f(b)-f(a)$ 与 $b-a$：直接对 $f$ 用拉格朗日；\n- 出现 $f'(\\xi) = g(\\xi)$：令 $F(x) = f(x) - \\int g$；\n- 出现两个中值 $\\xi,\\eta$：对两个区间分别用定理再联立。"},
            {"函数在 x=0 处连续但不可导的例子有哪些？",
                    "经典例子：\n- $f(x)=|x|$：左右导数分别为 $-1$、$1$；\n- $f(x)=x^{2/3}$：导数在 0 处趋于无穷；\n- $f(x)=x\\sin(1/x)$（$x\\ne 0$），$f(0)=0$：连续但导数振荡不存在。\n\n判断不可导要分别看左右导数是否存在且相等。"},
            {"帮我看看这个错题：lim_{x→0}(1-cos x)/x²",
                    "$1-\\cos x \\sim \\frac{x^2}{2}$，所以极限是 $\\frac{1}{2}$。\n\n常见错误是把它当成 $0/0$ 后直接求导两次却没化简，或者误用 $1-\\cos x \\sim x^2$。\n\n建议记住常用等价无穷小：$1-\\cos x \\sim x^2/2$，$\\tan x - \\sin x \\sim x^3/2$。"},
            {"为什么幂级数在端点处要单独讨论敛散性？",
                    "因为幂级数的收敛半径 $R$ 只保证 $|x-x_0|<R$ 内绝对收敛、$>R$ 发散，**端点 $x=x_0\\pm R$ 处定理不下结论**。\n\n端点处把 $x$ 代入会得到常数项级数，需用 p 级数、莱布尼茨判别法等单独判断，从而确定收敛域是开区间还是闭区间。"},
            {"方向导数和梯度的关系是什么？",
                    "梯度 $\\nabla f$ 是方向导数取最大值的方向，最大值为 $|\\nabla f|$。\n\n沿单位向量 $\\mathbf{l}$ 的方向导数：\n$$\\frac{\\partial f}{\\partial \\mathbf{l}} = \\nabla f \\cdot \\mathbf{l} = |\\nabla f|\\cos\\theta$$\n\n所以梯度方向是函数增长最快的方向，负梯度是下降最快的方向。"},
            {"这道证明题能用反证法吗？",
                    "可以，但先看结论形式：\n- 结论是“不存在”“唯一”“至少存在一个”时反证法往往最顺；\n- 结论是等式且条件为不等式时，反证法也常有效。\n\n注意反证法要先**明确否定结论**，再推出与已知条件或定理矛盾，不能中途直接假设结论成立。"}
    };

    private static final String[][] WRONG_TEMPLATES = {
            {"求极限 $\\lim_{x\\to 2}\\frac{x^2-4}{x-2}$ 的值是（ ）", "SINGLE", "0/0 型，约去 $x-2$ 后代入得 4。", "A", "C", "概念混淆", "把 $x=2$ 直接代入导致 0/0，未做因式分解。"},
            {"计算 $\\int_0^1 x e^x\\,dx$。", "FILL", "分部积分：$(x-1)e^x$，代入上下限得 1。", "e", "1", "计算失误", "分部积分时 $\\int e^x dx$ 符号出错。"},
            {"判断级数 $\\sum_{n=1}^{\\infty}\\frac{1}{n^2}$ 的敛散性。", "JUDGE", "p 级数 $p=2>1$，收敛。", "发散", "收敛", "方法不当", "与调和级数类比错误，未使用 p 级数判别法。"},
            {"设 $f(x)=|x|$，则 $f'(0)$ 等于（ ）", "SINGLE", "左右导数分别为 -1、1，故不可导。", "0", "不存在", "审题偏差", "只看到图像在 0 处有定义，忽略了左右导数不相等。"},
            {"求微分方程 $y'=2xy$ 的通解。", "FILL", "分离变量得 $y=Ce^{x^2}$。", "y=Ce^{2x}", "y=Ce^{x^2}", "概念混淆", "把 $\\int 2x dx$ 误算成 $2x$。"},
            {"求 $\\lim_{x\\to 0}\\frac{1-\\cos x}{x^2}$。", "FILL", "等价无穷小 $1-\\cos x\\sim x^2/2$，极限为 $1/2$。", "1", "1/2", "概念混淆", "误用 $1-\\cos x\\sim x^2$。"},
            {"函数 $f(x)=x^3$ 在 $x=0$ 处的切线斜率为（ ）", "SINGLE", "$f'(x)=3x^2$，$f'(0)=0$。", "3", "0", "计算失误", "求导公式 $x^3\\to 3x^2$ 代入时误算。"},
            {"求 $\\int \\frac{1}{x}dx$。", "FILL", "$\\ln|x|+C$。", "ln x", "ln|x|+C", "审题偏差", "漏掉绝对值与积分常数。"},
            {"设 $z=x^2y$，求 $\\frac{\\partial z}{\\partial x}$。", "FILL", "对 $x$ 求偏导把 $y$ 当常数，得 $2xy$。", "2x", "2xy", "概念混淆", "求偏导时未把另一变量视为常数。"},
            {"求 $\\lim_{n\\to\\infty}\\left(1+\\frac{1}{n}\\right)^n$。", "FILL", "重要极限，结果为 $e$。", "1", "e", "方法不当", "误以为底数趋于 1 则整体趋于 1。"}
    };

    private final UserRepository userRepository;
    private final ClassInfoRepository classInfoRepository;
    private final ClassTeacherConfigRepository configRepository;
    private final KnowledgePointRepository knowledgePointRepository;
    private final StudentKpMasteryRepository masteryRepository;
    private final InteractionRecordRepository interactionRepository;
    private final WrongQuestionRepository wrongQuestionRepository;
    private final ReportRepository reportRepository;
    private final PasswordHasher passwordHasher;
    private final JsonHelper jsonHelper;
    private final AppProperties appProperties;

    public DemoDataSeeder(UserRepository userRepository,
                          ClassInfoRepository classInfoRepository,
                          ClassTeacherConfigRepository configRepository,
                          KnowledgePointRepository knowledgePointRepository,
                          StudentKpMasteryRepository masteryRepository,
                          InteractionRecordRepository interactionRepository,
                          WrongQuestionRepository wrongQuestionRepository,
                          ReportRepository reportRepository,
                          PasswordHasher passwordHasher,
                          JsonHelper jsonHelper,
                          AppProperties appProperties) {
        this.userRepository = userRepository;
        this.classInfoRepository = classInfoRepository;
        this.configRepository = configRepository;
        this.knowledgePointRepository = knowledgePointRepository;
        this.masteryRepository = masteryRepository;
        this.interactionRepository = interactionRepository;
        this.wrongQuestionRepository = wrongQuestionRepository;
        this.reportRepository = reportRepository;
        this.passwordHasher = passwordHasher;
        this.jsonHelper = jsonHelper;
        this.appProperties = appProperties;
    }

    @Override
    @Transactional
    public void run(String... args) {
        if (!appProperties.isDemoData()) {
            log.info("app.demo-data=false，跳过演示数据初始化");
            return;
        }
        if (userRepository.count() > 0) {
            log.info("已存在用户数据，跳过演示数据初始化");
            return;
        }
        String passwordHash = passwordHasher.hash(DEMO_PASSWORD);

        UserInfo teacher1 = createUser("teacher1", passwordHash, "王老师", Role.TEACHER, "C-GS-01",
                "teacher1@example.com", "13900000001", null, null);
        UserInfo teacher2 = createUser("teacher2", passwordHash, "李老师", Role.TEACHER, "C-GS-02",
                "teacher2@example.com", "13900000002", null, null);

        createClass("C-GS-01", "考研高数强化班", "高等数学", teacher1);
        createClass("C-GS-02", "考研高数基础班", "高等数学", teacher2);

        UserInfo student1 = createUser("student1", passwordHash, "张同学", Role.STUDENT, "C-GS-01",
                "student1@example.com", "13800000001", "华东理工大学", 2027);
        UserInfo student2 = createUser("student2", passwordHash, "李同学", Role.STUDENT, "C-GS-01",
                "student2@example.com", "13800000002", "上海大学", 2027);
        UserInfo student3 = createUser("student3", passwordHash, "王同学", Role.STUDENT, "C-GS-01",
                "student3@example.com", "13800000003", "同济大学", 2027);
        UserInfo student4 = createUser("student4", passwordHash, "赵同学", Role.STUDENT, "C-GS-02",
                "student4@example.com", "13800000004", "东华大学", 2028);
        UserInfo student5 = createUser("student5", passwordHash, "陈同学", Role.STUDENT, "C-GS-02",
                "student5@example.com", "13800000005", "上海理工大学", 2028);

        List<UserInfo> students = List.of(student1, student2, student3, student4, student5);

        createConfig("C-GS-01", AnswerMode.MIXED, 3,
                scopeJson("ALL", List.of(), List.of()),
                kbAccessJson(true, true, true, false),
                jsonHelper.write(List.of("级数")),
                teacher1, LocalDateTime.now().minusDays(9));
        createConfig("C-GS-02", AnswerMode.GUIDED, 2,
                scopeJson("ALL", List.of(), List.of()),
                kbAccessJson(true, true, true, false),
                jsonHelper.write(List.of()),
                teacher2, LocalDateTime.now().minusDays(12));

        List<KnowledgePoint> points = knowledgePointRepository.findAllByOrderByOrderIndexAsc();
        if (points.isEmpty()) {
            log.warn("知识点目录为空，跳过掌握度/报告种子");
            return;
        }

        Map<Long, List<StudentKpMastery>> masteryByStudent = new LinkedHashMap<>();
        int[] weakIdxCursor = {4, 17, 29, 40, 51};
        double[] bases = {0.56, 0.30, 0.80, 0.42, 0.38};
        int[] weakIdxMeta = {6, 24, 12, 18, 15};
        for (int i = 0; i < students.size(); i++) {
            UserInfo student = students.get(i);
            Random random = new Random(20261025L + i * 131L);
            int weakCount = weakIdxMeta[i];
            List<Integer> weakIndexes = new ArrayList<>();
            for (int k = 0; k < weakCount; k++) {
                weakIndexes.add((weakIdxCursor[i] + k * 7) % points.size());
            }
            List<StudentKpMastery> rows = new ArrayList<>();
            for (int j = 0; j < points.size(); j++) {
                KnowledgePoint point = points.get(j);
                double mastery;
                if (weakIndexes.contains(j)) {
                    mastery = 0.08 + random.nextDouble() * 0.18;
                } else {
                    mastery = bases[i] + (random.nextDouble() - 0.5) * 0.34;
                }
                mastery = round2(Math.max(0.02, Math.min(0.98, mastery)));
                int attempts = 2 + random.nextInt(7);
                int correct = (int) Math.round(attempts * Math.max(0.1, Math.min(0.95, mastery + 0.12)));
                correct = Math.min(correct, attempts);
                StudentKpMastery row = new StudentKpMastery();
                row.setStudentId(student.getId());
                row.setKpId(point.getKpId());
                row.setMastery(mastery);
                row.setAttempts(attempts);
                row.setCorrectCount(correct);
                row.setUpdatedAt(LocalDateTime.now().minusDays(random.nextInt(20)).minusHours(random.nextInt(8)));
                rows.add(row);
            }
            masteryRepository.saveAll(rows);
            masteryByStudent.put(student.getId(), rows);
        }

        for (int i = 0; i < students.size(); i++) {
            UserInfo student = students.get(i);
            createInteractions(student, i);
            createWrongQuestions(student, points, i);
            createReports(student, points, masteryByStudent.get(student.getId()), i);
        }

        log.info("演示数据初始化完成：班级 2 个、用户 {} 个、知识点 {} 个",
                userRepository.count(), points.size());
    }

    private UserInfo createUser(String username, String passwordHash, String displayName, Role role,
                                String classId, String email, String phone, String targetSchool, Integer examYear) {
        UserInfo user = new UserInfo();
        user.setUsername(username);
        user.setPasswordHash(passwordHash);
        user.setDisplayName(displayName);
        user.setRole(role);
        user.setClassId(classId);
        user.setEmail(email);
        user.setPhone(phone);
        user.setTargetSchool(targetSchool);
        user.setExamYear(examYear);
        user.setCreatedAt(LocalDateTime.now().minusDays(60));
        return userRepository.save(user);
    }

    private void createClass(String classId, String className, String subject, UserInfo teacher) {
        ClassInfo info = new ClassInfo();
        info.setClassId(classId);
        info.setClassName(className);
        info.setSubject(subject);
        info.setTeacherId(teacher.getId());
        info.setTeacherName(teacher.getDisplayName());
        classInfoRepository.save(info);
    }

    private String scopeJson(String mode, List<String> chapters, List<String> kpIds) {
        return jsonHelper.write(Maps.of("mode", mode, "chapters", chapters, "kpIds", kpIds));
    }

    private String kbAccessJson(boolean kb1, boolean kb2, boolean kb3, boolean kb4) {
        return jsonHelper.write(Maps.of("kb1", kb1, "kb2", kb2, "kb3", kb3, "kb4", kb4));
    }

    private void createConfig(String classId, AnswerMode mode, int maxDifficulty, String scope, String kbAccess,
                              String disabledTopics, UserInfo teacher, LocalDateTime updatedAt) {
        ClassTeacherConfig config = new ClassTeacherConfig();
        config.setClassId(classId);
        config.setAnswerMode(mode);
        config.setMaxDifficulty(maxDifficulty);
        config.setKnowledgeScope(scope);
        config.setBoundaryRules(BOUNDARY_RULES);
        config.setKbAccess(kbAccess);
        config.setDisabledTopics(disabledTopics);
        config.setUpdatedAt(updatedAt);
        config.setUpdatedBy(teacher.getId());
        configRepository.save(config);
    }

    private void createInteractions(UserInfo student, int studentIndex) {
        Random random = new Random(7100L + studentIndex * 53L);
        int count = 22 + random.nextInt(16);
        RecordType[] cycle = {RecordType.QA, RecordType.QA, RecordType.QA, RecordType.PRACTICE,
                RecordType.QA, RecordType.DIAGNOSIS, RecordType.QA, RecordType.PLAN};
        for (int i = 0; i < count; i++) {
            RecordType type = cycle[i % cycle.length];
            String[] template = QA_TEMPLATES[random.nextInt(QA_TEMPLATES.length)];
            InteractionRecord record = new InteractionRecord();
            record.setStudentId(student.getId());
            record.setClassId(student.getClassId());
            record.setType(type);
            record.setIntent(intentOf(type));
            record.setUserMessage(template[0]);
            record.setAiResponse(answerOf(type, template[1]));
            record.setSources(type == RecordType.QA ? sourceJson(random.nextInt(3), 1) : "[]");
            String kpId = "kp" + String.format("%03d", 1 + random.nextInt(67));
            record.setKpIds(jsonHelper.write(List.of(kpId)));
            record.setKpNames(jsonHelper.write(List.of(kpNameOr(kpId))));
            record.setBlocked(false);
            record.setCreatedAt(LocalDateTime.now()
                    .minusDays(random.nextInt(30))
                    .minusHours(random.nextInt(12))
                    .minusMinutes(random.nextInt(60)));
            interactionRepository.save(record);
        }
    }

    private String intentOf(RecordType type) {
        return switch (type) {
            case QA -> "qa";
            case DIAGNOSIS -> "diagnose";
            case PRACTICE -> "practice";
            case PLAN -> "plan";
        };
    }

    private String answerOf(RecordType type, String qaAnswer) {
        return switch (type) {
            case QA -> qaAnswer;
            case DIAGNOSIS -> "已为你生成一份诊断报告，可在「报告库」查看，重点讲解薄弱知识点与下一步建议。";
            case PRACTICE -> "已按当前薄弱知识点生成一组分层练习，建议先独立完成再看思路提示。";
            case PLAN -> "已结合你的掌握度生成一份学习计划，可在「学习计划」中逐日打卡。";
        };
    }

    private String kpNameOr(String kpId) {
        return knowledgePointRepository.findById(kpId).map(KnowledgePoint::getKpName).orElse("高等数学核心知识点");
    }

    private String sourceJson(int kpOffset, int count) {
        List<Map<String, Object>> sources = new ArrayList<>();
        String[] kbIds = {"kb1-outline", "kb2-textbook", "kb3-exercise"};
        String[] kbNames = {"KB1", "KB2", "KB3"};
        String[] titles = {"高等数学课程大纲-知识库版.md", "高等数学教材讲义.md", "考研高数典型题集.md"};
        for (int i = 0; i < count; i++) {
            int index = (kpOffset + i) % kbIds.length;
            sources.add(Maps.of(
                    "documentId", kbIds[index],
                    "kb", kbNames[index],
                    "title", titles[index],
                    "excerpt", "该章节给出了相关定义、定理与典型例题，可结合本节内容复习。",
                    "score", round2(0.35 + 0.1 * i),
                    "kpId", "kp" + String.format("%03d", 1 + (kpOffset * 7 + i * 3) % 67),
                    "chunkId", "c-" + (100 + index * 10 + i)));
        }
        return jsonHelper.write(sources);
    }

    private void createWrongQuestions(UserInfo student, List<KnowledgePoint> points, int studentIndex) {
        Random random = new Random(9100L + studentIndex * 41L);
        int count = 5 + random.nextInt(6);
        for (int i = 0; i < count; i++) {
            String[] template = WRONG_TEMPLATES[(i + studentIndex) % WRONG_TEMPLATES.length];
            KnowledgePoint point = points.get((i * 9 + studentIndex * 5) % points.size());
            WrongQuestion wrong = new WrongQuestion();
            wrong.setStudentId(student.getId());
            wrong.setClassId(student.getClassId());
            wrong.setKpId(point.getKpId());
            wrong.setKpName(point.getKpName());
            wrong.setQuestionText(template[0]);
            wrong.setQuestionType(template[1]);
            wrong.setDifficulty(1 + random.nextInt(3));
            wrong.setStudentAnswer(template[3]);
            wrong.setCorrectAnswer(template[4]);
            wrong.setErrorType(template[5]);
            wrong.setAnalysis(template[6]);
            wrong.setSourceType(random.nextBoolean() ? "PRACTICE" : "DIAGNOSIS");
            wrong.setReviewed(random.nextDouble() < 0.45);
            wrong.setCreatedAt(LocalDateTime.now()
                    .minusDays(random.nextInt(28))
                    .minusHours(random.nextInt(10)));
            wrongQuestionRepository.save(wrong);
        }
    }

    private void createReports(UserInfo student, List<KnowledgePoint> points,
                               List<StudentKpMastery> masteryRows, int studentIndex) {
        List<StudentKpMastery> sorted = new ArrayList<>(masteryRows);
        sorted.sort((a, b) -> Double.compare(a.getMastery(), b.getMastery()));

        List<Map<String, Object>> weakTop5 = new ArrayList<>();
        for (int i = 0; i < Math.min(5, sorted.size()); i++) {
            StudentKpMastery row = sorted.get(i);
            KnowledgePoint point = findKp(points, row.getKpId());
            if (point == null) {
                continue;
            }
            weakTop5.add(Maps.of("kpId", point.getKpId(), "kpName", point.getKpName(),
                    "mastery", round2(row.getMastery()),
                    "accuracy", row.getAttempts() == 0 ? 0.0
                            : round2((double) row.getCorrectCount() / row.getAttempts())));
        }

        int total = 15;
        int correct = 5 + (studentIndex == 2 ? 8 : studentIndex == 0 ? 5 : 2);
        correct = Math.min(correct, total);
        int score = (int) Math.round(correct * 100.0 / total);
        String level = levelOf(score);

        List<Map<String, Object>> errorSummary = new ArrayList<>();
        String[] errorTypes = {"概念混淆", "计算失误", "审题偏差", "方法不当"};
        int[] errorCounts = {3, 2, 2, 1};
        for (int i = 0; i < errorTypes.length; i++) {
            errorSummary.add(Maps.of("errorType", errorTypes[i], "count", errorCounts[i],
                    "ratio", round2((double) errorCounts[i] / total),
                    "questionIds", List.of("q-" + (i * 3 + 1), "q-" + (i * 3 + 2))));
        }

        List<String> advice = List.of(
                "优先巩固极限与导数的基础计算，每天保持 20 分钟基本题型训练。",
                "建立错题复盘习惯，按错误类型归类，三天后重做一次。",
                "复习时先看章节知识框架，再做综合题，避免只刷题不总结。");

        Map<String, Object> diagnosisContent = Maps.of(
                "mode", "FULL",
                "total", total,
                "correctCount", correct,
                "score", score,
                "level", level,
                "weakTop5", weakTop5,
                "errorSummary", errorSummary,
                "advice", advice);

        Report diagnosis = createReport(student, ReportType.DIAGNOSIS, ReportStatus.COMPLETED,
                "全面诊断报告 · " + LocalDate.now().minusDays(7).toString(),
                "整体水平：" + level + "；薄弱知识点 " + weakTop5.size() + " 个，建议按计划逐项突破。",
                diagnosisContent,
                LocalDateTime.now().minusDays(7).withHour(20).withMinute(30).withSecond(0).withNano(0));

        int planDays = studentIndex == 2 ? 5 : 7;
        int doneDays = studentIndex == 0 ? 3 : studentIndex == 1 ? 2 : studentIndex == 2 ? 4 : 1;
        LocalDate startDate = LocalDate.now().minusDays(planDays - 1);
        Map<String, Object> planContent = buildPlanContent(student, points, sorted, "WEEK", planDays, startDate,
                doneDays, "围绕薄弱 TOP5 逐日突破。", null);
        createReport(student, ReportType.PLAN, ReportStatus.COMPLETED,
                planDays + "天高数强化计划",
                "围绕薄弱知识点逐日突破，每天学习 + 练习 + 复盘。",
                planContent,
                LocalDateTime.now().minusDays(6).withHour(18).withMinute(0).withSecond(0).withNano(0));

        List<Map<String, Object>> practiceQuestions = buildPracticeQuestions(points, sorted, 3);
        Map<String, Object> practiceContent = Maps.of(
                "batchId", "",
                "layer", "B",
                "kpIds", practiceQuestions.stream().map(q -> q.get("kpId")).toList(),
                "kpNames", practiceQuestions.stream().map(q -> q.get("kpName")).toList(),
                "questions", practiceQuestions,
                "guidance", "先独立完成，再看提示；本页不提供最终答案。");
        Report practice = createReport(student, ReportType.PRACTICE, ReportStatus.COMPLETED,
                "分层练习 · B 级",
                "针对薄弱知识点生成的 3 道分层练习，建议先独立完成。",
                practiceContent,
                LocalDateTime.now().minusDays(3).withHour(21).withMinute(10).withSecond(0).withNano(0));
        practiceContent.put("batchId", "p-" + practice.getId());
        practice.setContent(jsonHelper.write(practiceContent));
        reportRepository.save(practice);

        if (studentIndex == 0) {
            Map<String, Object> secondPlan = buildPlanContent(student, points, sorted, "MONTH", 14,
                    LocalDate.now().minusDays(9), 4, "两周内完成高数第一轮强化复习。", null);
            createReport(student, ReportType.PLAN, ReportStatus.COMPLETED,
                    "14天高数强化计划",
                    "第一轮强化复习：覆盖高数核心章节，逐日推进。",
                    secondPlan,
                    LocalDateTime.now().minusDays(9).withHour(19).withMinute(0).withSecond(0).withNano(0));
        }
    }

    private Report createReport(UserInfo student, ReportType type, ReportStatus status, String title,
                                String summary, Map<String, Object> content, LocalDateTime createdAt) {
        Report report = new Report();
        report.setStudentId(student.getId());
        report.setClassId(student.getClassId());
        report.setType(type);
        report.setTitle(title);
        report.setSummary(summary);
        report.setStatus(status);
        report.setContent(jsonHelper.write(content));
        report.setCreatedAt(createdAt);
        report.setUpdatedAt(createdAt);
        return reportRepository.save(report);
    }

    private Map<String, Object> buildPlanContent(UserInfo student, List<KnowledgePoint> points,
                                                 List<StudentKpMastery> sorted, String period, int daysCount,
                                                 LocalDate startDate, int doneDays, String summary,
                                                 List<String> focusKpIds) {
        List<Map<String, Object>> days = new ArrayList<>();
        List<String> focus = focusKpIds == null || focusKpIds.isEmpty()
                ? sorted.stream().limit(daysCount).map(StudentKpMastery::getKpId).toList()
                : focusKpIds;
        for (int i = 0; i < daysCount; i++) {
            String kpId = focus.get(i % focus.size());
            KnowledgePoint point = findKp(points, kpId);
            String kpName = point == null ? kpId : point.getKpName();
            LocalDate date = startDate.plusDays(i);
            boolean done = i < doneDays;
            days.add(Maps.of(
                    "dayIndex", i + 1,
                    "date", date.toString(),
                    "kpId", kpId,
                    "kpName", kpName,
                    "goal", "掌握 " + kpName + " 的核心方法与典型题型",
                    "study", Maps.of(
                            "summary", "先回顾定义与定理，再对照例题理解解题步骤。",
                            "points", List.of("梳理该知识点的定义与常见变形", "整理 2 个典型例题的解题套路"),
                            "example", "结合教材例题，写出完整解题过程并标注关键步骤。"),
                    "practice", Maps.of("questions", buildPracticeQuestions(points, sorted, 2)),
                    "review", Maps.of(
                            "summary", "当天结束后用 10 分钟复述知识框架，并重做错题。",
                            "checklist", List.of("能独立写出该知识点的定义", "能独立完成 2 道基础题", "错题已复盘")),
                    "done", done,
                    "completedAt", done ? date.atTime(20, 30).toString() : null));
        }
        return Maps.of(
                "id", null,
                "title", daysCount + "天高数强化计划",
                "period", period,
                "daysCount", daysCount,
                "startDate", startDate.toString(),
                "summary", summary,
                "createdAt", LocalDateTime.now().toString(),
                "days", days);
    }

    private List<Map<String, Object>> buildPracticeQuestions(List<KnowledgePoint> points,
                                                             List<StudentKpMastery> sorted, int count) {
        List<Map<String, Object>> questions = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            String kpId = sorted.get(i % sorted.size()).getKpId();
            KnowledgePoint point = findKp(points, kpId);
            String kpName = point == null ? kpId : point.getKpName();
            questions.add(Maps.of(
                    "questionId", "seed-q-" + (i + 1),
                    "index", i + 1,
                    "kpId", kpId,
                    "kpName", kpName,
                    "difficulty", 2,
                    "type", i % 2 == 0 ? "FILL" : "SINGLE",
                    "stem", "关于「" + kpName + "」的计算题：请写出完整解题过程。",
                    "options", List.of(),
                    "hint", "先回顾该知识点的定义与常用公式。"));
        }
        return questions;
    }

    private KnowledgePoint findKp(List<KnowledgePoint> points, String kpId) {
        for (KnowledgePoint point : points) {
            if (point.getKpId().equals(kpId)) {
                return point;
            }
        }
        return null;
    }

    private String levelOf(int score) {
        if (score >= 85) {
            return "优秀";
        }
        if (score >= 70) {
            return "良好";
        }
        if (score >= 55) {
            return "一般";
        }
        return "待提升";
    }

    private double round2(double value) {
        return Math.round(value * 100.0) / 100.0;
    }
}
