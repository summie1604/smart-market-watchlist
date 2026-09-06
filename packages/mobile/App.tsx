import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import type {
  AssessmentView,
  AttentionItemView,
  ExplainerAnswerView,
  ReviewPageView,
  WatchPointView,
} from "@smart-market-watchlist/shared";
import { createMobileApi } from "./src/api";

const api = createMobileApi({
  baseUrl: process.env.EXPO_PUBLIC_API_URL ?? "http://127.0.0.1:8000",
});

export default function App(): React.JSX.Element {
  const [review, setReview] = useState<ReviewPageView | null>(null);
  const [selected, setSelected] = useState<AttentionItemView | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    try {
      setError("");
      setReview(await api.openReview());
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "The brief could not load.",
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(async (): Promise<void> => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const acknowledge = useCallback(
    async (pointId: string): Promise<void> => {
      try {
        await api.acknowledgeWatchPoint(pointId);
        await load();
      } catch {
        // A failed acknowledgement leaves the notice in place, which is the safe
        // direction: it keeps asking rather than silently disappearing unseen.
      }
    },
    [load],
  );

  const complete = useCallback(async (): Promise<void> => {
    if (!review) return;
    try {
      setError("");
      await api.completeReview(review.review_id);
      await load();
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The review could not be completed.",
      );
    }
  }, [load, review]);

  const title = useMemo(
    () =>
      review?.attention_count
        ? `${review.attention_count} ${review.attention_count === 1 ? "development needs" : "developments need"} attention`
        : "You’re all caught up",
    [review],
  );

  if (!review && !error) {
    return (
      <SafeAreaView style={styles.loading}>
        <ActivityIndicator size="large" color="#142b22" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.brand}>Smart Market Watchlist</Text>
        <Text style={styles.kicker}>NEEDS ATTENTION</Text>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.subtitle}>
          Evidence-ranked developments since your last completed review.
        </Text>
      </View>
      {error ? (
        <View style={styles.error}>
          <Text style={styles.errorTitle}>Could not load the brief</Text>
          <Text>{error}</Text>
        </View>
      ) : null}
      <FlatList
        data={review?.needs_attention ?? []}
        keyExtractor={(item) => item.assessment.event_id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void refresh()}
          />
        }
        ListHeaderComponent={
          review ? (
            <>
              <Reached
                points={review.triggered_watch_points}
                onSeen={acknowledge}
              />
              {review.unable.length > 0 ? (
                <CoverageNotice review={review} />
              ) : null}
            </>
          ) : null
        }
        renderItem={({ item }) => (
          <AttentionCard item={item} onPress={() => setSelected(item)} />
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>
              Nothing new needs your attention.
            </Text>
            <Text style={styles.muted}>
              Pull down to check again. Coverage gaps are shown above, never
              counted as quiet.
            </Text>
          </View>
        }
        ListFooterComponent={
          review ? (
            <Pressable style={styles.complete} onPress={() => void complete()}>
              <Text style={styles.completeText}>Mark review complete</Text>
            </Pressable>
          ) : null
        }
      />
      <Detail item={selected} onClose={() => setSelected(null)} />
    </SafeAreaView>
  );
}

function CoverageNotice({
  review,
}: {
  review: ReviewPageView;
}): React.JSX.Element {
  return (
    <View style={styles.coverageNotice}>
      <Text style={styles.errorTitle}>Coverage incomplete</Text>
      <Text style={styles.muted}>
        Could not fully evaluate{" "}
        {review.unable.map((line) => line.symbol).join(", ")}.
      </Text>
    </View>
  );
}

/**
 * Levels the reader asked to be told about, once a stored close has crossed them (D37).
 *
 * Pull-based on every surface: the notice waits at the top of the brief for the next
 * visit. Nothing is pushed to the device, because a product about protecting attention
 * does not get to interrupt.
 */
function Reached({
  points,
  onSeen,
}: {
  points: WatchPointView[];
  onSeen: (pointId: string) => Promise<void>;
}): React.JSX.Element | null {
  if (points.length === 0) return null;
  return (
    <View style={styles.reached}>
      <Text style={styles.reachedTitle}>You asked to be told</Text>
      {points.map((point) => (
        <View key={point.point_id} style={styles.reachedRow}>
          <Text style={styles.reachedText}>
            {point.symbol} — {point.note || "your level"}: closed{" "}
            {point.triggered_close} on {point.triggered_on},{" "}
            {point.direction === "ABOVE" ? "at or above" : "at or below"}{" "}
            {point.level}.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Mark the ${point.symbol} level as seen`}
            onPress={() => void onSeen(point.point_id)}
          >
            <Text style={styles.reachedSeen}>Got it</Text>
          </Pressable>
        </View>
      ))}
    </View>
  );
}

function AttentionCard({
  item,
  onPress,
}: {
  item: AttentionItemView;
  onPress: () => void;
}): React.JSX.Element {
  const assessment = item.assessment;
  return (
    // A list is one column on every phone, so the layout question the web board has does
    // not arise here. What has to match across surfaces is the *information*: the same
    // three axes, in the same order, worded the same way.
    <Pressable
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`Open ${item.symbol} development`}
    >
      <View style={styles.cardTop}>
        <Text style={styles.symbol}>{item.symbol}</Text>
        <Text style={[styles.badge, badgeStyle(assessment.attention)]}>
          {assessment.attention}
        </Text>
      </View>
      <Text style={styles.company}>{item.company}</Text>
      <Text style={styles.headline}>{assessment.description}</Text>
      <Text style={styles.proof}>
        {assessment.confidence} confidence ·{" "}
        {assessment.corroboration.independent_source_count} independent sources
        · {assessment.source_standing_label}
      </Text>
      <Text style={styles.open}>Read evidence and reasoning →</Text>
    </Pressable>
  );
}

function Detail({
  item,
  onClose,
}: {
  item: AttentionItemView | null;
  onClose: () => void;
}): React.JSX.Element {
  const assessment: AssessmentView | undefined = item?.assessment;
  return (
    <Modal
      visible={item !== null}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.screen}>
        <ScrollView contentContainerStyle={styles.detail}>
          <Pressable onPress={onClose} accessibilityRole="button">
            <Text style={styles.close}>Close</Text>
          </Pressable>
          {item && assessment ? (
            <>
              <Text style={styles.kicker}>
                {item.symbol} · {assessment.event_type}
              </Text>
              <Text style={styles.detailTitle}>{assessment.description}</Text>
              <View style={styles.factRow}>
                <Text>{assessment.attention} attention</Text>
                <Text>{assessment.confidence} confidence</Text>
              </View>
              {/* A third axis: what kind of source said it. Separate from how much it
                  matters and from how sure we are (D36). */}
              <Text style={styles.standing}>
                Source: {assessment.source_standing_label}
              </Text>
              {assessment.contradiction.state !== "STANDING" ? (
                <View style={styles.contradiction}>
                  <Text style={styles.errorTitle}>
                    {assessment.contradiction.state}
                  </Text>
                  <Text>{assessment.contradiction.detail}</Text>
                </View>
              ) : null}
              <Text style={styles.sectionTitle}>Why this is here</Text>
              {assessment.reasons.map((reason) => (
                <Text key={reason.code} style={styles.reason}>
                  • {reason.detail}
                </Text>
              ))}
              <Text style={styles.sectionTitle}>Evidence</Text>
              {assessment.evidence.map((evidence) => (
                <View key={evidence.ref} style={styles.evidence}>
                  <Text style={styles.evidenceName}>
                    {evidence.publisher || evidence.source}
                  </Text>
                  <Text style={styles.muted}>
                    {evidence.standing_label} ·{" "}
                    {new Date(evidence.published_at).toLocaleDateString()}
                  </Text>
                </View>
              ))}
              <Text style={styles.sectionTitle}>Coverage</Text>
              <Text style={styles.reason}>
                {assessment.coverage.complete
                  ? "Available source coverage was complete."
                  : assessment.coverage.note}
              </Text>
              <Ask symbol={item.symbol} />
            </>
          ) : null}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

/**
 * The bounded explainer on a phone (D35).
 *
 * Deliberately a short list of questions rather than a text field: the answerable set is
 * fixed, and on a small screen offering a keyboard would invite the open conversation the
 * product does not have. The same server composes the same answer for both clients — this
 * one only renders it, including the window and the coverage gap that make it checkable.
 */
function Ask({ symbol }: { symbol: string }): React.JSX.Element {
  const [answer, setAnswer] = useState<ExplainerAnswerView | null>(null);
  const [asking, setAsking] = useState("");

  const ask = useCallback(
    async (question: string): Promise<void> => {
      setAsking(question);
      try {
        setAnswer(await api.explain(symbol, question));
      } catch {
        setAnswer(null);
      } finally {
        setAsking("");
      }
    },
    [symbol],
  );

  return (
    <>
      <Text style={styles.sectionTitle}>Ask about this company</Text>
      <View style={styles.askRow}>
        {QUESTIONS.map((question) => (
          <Pressable
            key={question}
            accessibilityRole="button"
            style={styles.askChip}
            onPress={() => void ask(question)}
          >
            <Text style={styles.askChipText}>
              {asking === question ? "…" : question}
            </Text>
          </Pressable>
        ))}
      </View>
      {answer ? (
        <View style={styles.answer}>
          <Text style={styles.muted}>
            Evidence window: {answer.window.basis} ·{" "}
            {answer.window.assessments_considered} considered
          </Text>
          {!answer.coverage.complete ? (
            <Text style={styles.errorTitle}>
              Coverage gap — {answer.coverage.note}
            </Text>
          ) : null}
          {answer.statements.map((statement, index) => (
            <Text
              key={`${index}-${statement.text.slice(0, 16)}`}
              style={styles.reason}
            >
              • {statement.text}
              {statement.event_ids.length > 0
                ? ` (${statement.event_ids.length} records)`
                : ""}
            </Text>
          ))}
          <Text style={styles.muted}>{answer.disclaimer}</Text>
        </View>
      ) : null}
    </>
  );
}

const QUESTIONS = [
  "What changed recently?",
  "Why does this need my attention?",
  "What could you not see?",
] as const;

function badgeStyle(attention: AssessmentView["attention"]): object {
  if (attention === "HIGH") return styles.high;
  if (attention === "MEDIUM") return styles.medium;
  return styles.low;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f4f3ee" },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f4f3ee",
  },
  header: { paddingHorizontal: 22, paddingTop: 18, paddingBottom: 16 },
  brand: {
    color: "#526158",
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 28,
  },
  kicker: {
    color: "#637067",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1.4,
    marginBottom: 7,
  },
  title: {
    color: "#142b22",
    fontSize: 30,
    fontWeight: "700",
    letterSpacing: -0.7,
  },
  subtitle: { color: "#637067", fontSize: 14, lineHeight: 20, marginTop: 8 },
  list: { paddingHorizontal: 16, paddingBottom: 40, flexGrow: 1 },
  card: {
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 18,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: "#e1e1da",
  },
  cardTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  symbol: { color: "#142b22", fontSize: 18, fontWeight: "800" },
  company: { color: "#637067", fontSize: 13, marginTop: 2 },
  badge: {
    overflow: "hidden",
    borderRadius: 20,
    paddingHorizontal: 9,
    paddingVertical: 5,
    fontSize: 11,
    fontWeight: "800",
  },
  high: { color: "#9f2d27", backgroundColor: "#fce9e7" },
  medium: { color: "#8a5a0a", backgroundColor: "#fff2d7" },
  low: { color: "#356348", backgroundColor: "#e6f2e9" },
  headline: {
    color: "#1d2b25",
    fontSize: 17,
    lineHeight: 24,
    fontWeight: "600",
    marginTop: 16,
  },
  proof: { color: "#637067", fontSize: 12, marginTop: 12 },
  open: { color: "#1f654a", fontSize: 13, fontWeight: "700", marginTop: 16 },
  empty: {
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 24,
    borderWidth: 1,
    borderColor: "#e1e1da",
  },
  emptyTitle: {
    color: "#142b22",
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 8,
  },
  muted: { color: "#6d756f", fontSize: 13, lineHeight: 19 },
  complete: {
    backgroundColor: "#142b22",
    borderRadius: 12,
    padding: 15,
    alignItems: "center",
    marginTop: 8,
  },
  completeText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  error: {
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 12,
    padding: 14,
    backgroundColor: "#fce9e7",
  },
  coverageNotice: {
    marginBottom: 12,
    borderRadius: 12,
    padding: 14,
    backgroundColor: "#fff2d7",
  },
  errorTitle: { color: "#8d2822", fontWeight: "700", marginBottom: 3 },
  detail: { padding: 22, paddingBottom: 60 },
  standing: { marginTop: 6, fontSize: 13, color: "#6b6357" },
  cardPressed: { opacity: 0.7 },
  reached: {
    borderLeftWidth: 3,
    borderLeftColor: "#2f6f4f",
    backgroundColor: "#ffffff",
    borderRadius: 10,
    padding: 12,
    marginBottom: 12,
    gap: 8,
  },
  reachedTitle: {
    fontSize: 12,
    letterSpacing: 1,
    color: "#2f6f4f",
    fontWeight: "700",
  },
  reachedRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  reachedText: { flex: 1, fontSize: 14, color: "#3d3a32" },
  reachedSeen: { fontSize: 13, color: "#2f6f4f", fontWeight: "600" },
  askRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  askChip: {
    borderWidth: 1,
    borderColor: "#c9c4b5",
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  askChipText: { fontSize: 13 },
  answer: {
    marginTop: 12,
    borderLeftWidth: 2,
    borderLeftColor: "#c9c4b5",
    paddingLeft: 10,
    gap: 4,
  },
  close: {
    color: "#1f654a",
    fontWeight: "700",
    textAlign: "right",
    marginBottom: 26,
  },
  detailTitle: {
    color: "#142b22",
    fontSize: 26,
    lineHeight: 34,
    fontWeight: "700",
  },
  factRow: {
    flexDirection: "row",
    gap: 18,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: "#dddcd5",
    paddingVertical: 14,
    marginTop: 22,
  },
  contradiction: {
    borderRadius: 12,
    backgroundColor: "#fce9e7",
    padding: 14,
    marginTop: 18,
  },
  sectionTitle: {
    color: "#142b22",
    fontSize: 16,
    fontWeight: "800",
    marginTop: 28,
    marginBottom: 8,
  },
  reason: { color: "#34433b", fontSize: 14, lineHeight: 21, marginBottom: 7 },
  evidence: {
    flexDirection: "row",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderColor: "#e1e1da",
    paddingVertical: 12,
  },
  evidenceName: { color: "#24382f", fontWeight: "600", flex: 1 },
});
