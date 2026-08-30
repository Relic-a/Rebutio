// ============================================================
// Demo fixtures only — replace with backend-provided content.
// Nothing here is a product decision; it exists so the app is
// fully demoable without a backend.
// ============================================================

import type { DebateReview, LearningPath, OnboardingPreferences, ProgressStats, SkillId } from "@/lib/types";

export type DebateTopicFixture = {
  id: string;
  topic: string;
  skill: SkillId;
  difficulty: "gentle" | "steady" | "sharp";
  turns: number;
  minutes: number;
  reminder: string;
  opponentLines: string[]; // one opponent response per user turn
};
export const mockDebateTopics: DebateTopicFixture[] = [
  {
    id: "cats-dogs",
    topic: "Cats are better pets than dogs.",
    skill: "take_a_side",
    difficulty: "gentle",
    turns: 3,
    minutes: 5,
    reminder: "Pick a side and hold it.",
    opponentLines: [
      "Sure, cats are low-maintenance — but low effort isn't the same as companionship. A pet that ignores you half the time isn't much of a friend, is it?",
      "You say cats fit busy lives. But isn't choosing a pet based on convenience a weak reason? Shouldn't we choose based on what we actually get back?",
      "One last push: if companionship is what matters, dogs win on every measure. What's the single strongest thing cats offer that dogs can't?",
    ],
  },
  {
    id: "uniforms",
    topic: "School uniforms are actually a good idea.",
    skill: "give_a_reason",
    difficulty: "gentle",
    turns: 3,
    minutes: 5,
    reminder: "Give one clear reason for your side.",
    opponentLines: [
      "Uniforms reduce pressure to dress a certain way — I can agree. But don't they also erase exactly the self-expression teenagers need to develop?",
      "Your discipline argument is common. Yet schools with uniforms and schools without often perform the same. Where does your 'structure' actually show up in results?",
      "Final point: if we want students ready for adult life, shouldn't they learn to make daily choices instead of obeying a dress code?",
    ],
  },
  {
    id: "social-media",
    topic: "Social media has made friendships worse.",
    skill: "counterpoint",
    difficulty: "steady",
    turns: 4,
    minutes: 6,
    reminder: "Don't just repeat your position. Respond directly to their strongest point.",
    opponentLines: [
      "Social media keeps friendships alive across distance. Someone who moved abroad still talks to their best friend every day. How is that worse?",
      "You blame the tool, not the habits. People who feel lonelier online were often lonely before. Isn't this a correlation, not a cause?",
      "Consider this: most people report they'd rather message a friend than call. Convenience beats depth — but is that social media's fault, or just what people prefer?",
      "Last challenge: if friendships online are shallower, maybe they were never going to be deep anyway. What does social media actually destroy?",
    ],
  },
  {
    id: "ai-jobs",
    topic: "AI will create more jobs than it destroys.",
    skill: "counterargument",
    difficulty: "steady",
    turns: 4,
    minutes: 6,
    reminder: "Make a counterargument, not just a defense.",
    opponentLines: [
      "Every technology shift created new work — cars killed stable work but created mechanics, roads, logistics. Why would AI be different?",
      "The new jobs will need skills most displaced workers don't have. A truck driver won't become a machine-learning engineer. Doesn't the transition itself break your argument?",
      "Productivity is already rising without new employment. Companies are absorbing gains into profits. What mechanism turns this round of automation into new jobs?",
      "One final push: 'history repeats' is a comfort, not a law. What if this time really is different in kind, not just degree?",
    ],
  },
  {
    id: "college",
    topic: "College is no longer worth the cost.",
    skill: "rebuttal",
    difficulty: "steady",
    turns: 4,
    minutes: 7,
    reminder: "Respond directly to their strongest point.",
    opponentLines: [
      "Graduates still earn roughly a million dollars more over a lifetime than non-graduates. That gap alone answers the cost question, doesn't it?",
      "The 'alternative' — skipping college — isn't neutral. Non-graduates face higher unemployment in every downturn. Where's your safe path?",
      "You mentioned trades, but electricians and plumbers also need paid training. Isn't the real problem the price of all credentials, not college itself?",
      "Final challenge: if college is a bad deal, why do employers still pay a premium for the degree? Markets disagree with you.",
    ],
  },
  {
    id: "algorithms",
    topic: "Governments should regulate addictive algorithms.",
    skill: "rebuttal",
    difficulty: "sharp",
    turns: 4,
    minutes: 7,
    reminder: "Address their argument head-on before restating yours.",
    opponentLines: [
      "Where do you draw the line? News, shopping, sports — anything can be engaging. A law against 'addictive design' would ban the whole internet.",
      "Adults have a right to choose how they spend attention. Should the state really parent a 34-year-old scrolling at midnight?",
      "Regulation moves slowly; feeds iterate weekly. By the time a rule passes, the product has changed. Isn't enforcement impossible by design?",
      "Last one: the harms are real but modest. Is losing an hour a night worth giving regulators power over software design?",
    ],
  },
  {
    id: "free-speech",
    topic: "Free speech should protect deliberately misleading speech.",
    skill: "evidence",
    difficulty: "sharp",
    turns: 5,
    minutes: 8,
    reminder: "Support your point with a concrete example.",
    opponentLines: [
      "Protecting lies protects the powerful. Think of the meals-disinformation cases — real people lost real trust. Where's your evidence that tolerance beats harm?",
      "Every democracy draws some line: fraud, defamation, incitement. You're just arguing about where the line is, so why frame it as absolute?",
      "You claim counter-speech cures bad speech — but studies show corrections rarely reach the original audience. What's your evidence that it works?",
      "Final challenge: if a platform algorithmically amplifies a known lie to millions, is that still 'speech' the state should hands-off?",
    ],
  },
  {
    id: "inequality",
    topic: "Economic inequality is an unavoidable consequence of individual liberty.",
    skill: "nuance",
    difficulty: "sharp",
    turns: 5,
    minutes: 8,
    reminder: "Compare competing principles — freedom vs. fairness.",
    opponentLines: [
      "Liberty produces unequal outcomes only when starting points are unequal. Tax-funded education flattens the field. Doesn't that break 'unavoidable'?",
      "Consider Sweden: high freedom rankings, much lower inequality. Doesn't that disprove your necessity claim outright?",
      "Inheritance alone creates permanent hierarchies regardless of talent. Is inherited advantage really a consequence of individual liberty?",
      "You say the trade-off is worth it — but you haven't shown it's a trade-off at all. What if we could keep liberty and reduce inequality?",
      "Final: 'unavoidable' is a very strong word. Are you defending inequality, or just excusing it?",
    ],
  },
  {
    id: "homework",
    topic: "Homework should be abolished in primary school.",
    skill: "back_it_up",
    difficulty: "gentle",
    turns: 4,
    minutes: 6,
    reminder: "Support your reason with a concrete example.",
    opponentLines: [
      "Practice matters. A child who reads twenty minutes at home simply outpaces one who doesn't. Doesn't skill need repetition?",
      "Homework teaches parents what school is teaching. Remove it and you cut families out of education. Is that a gain?",
      "Self-discipline is built by small obligations. Kids who never practice working alone hit a wall in secondary school. What replaces that training?",
      "Final point: research you cite says academic gains are tiny at that age — but 'tiny' isn't 'zero'. Why abolish rather than reform?",
    ],
  },
  {
    id: "remote-work",
    topic: "Remote work is better for most careers than office work.",
    skill: "concession",
    difficulty: "sharp",
    turns: 5,
    minutes: 8,
    reminder: "Concede part of their argument without abandoning your position.",
    opponentLines: [
      "Junior employees learn by overhearing senior people. Remote work deletes that osmosis. Can you really dismiss that cost?",
      "Promotions track visibility. Two equal workers, one in the office — the one seen gets the role. Isn't remote work a career tax?",
      "Offices aren't just desks — they're trust. Teams that have never met struggle in a crisis. Some friction is worth the cohesion, no?",
      "You'll say hybrid solves this. But hybrid means half the connections and all the coordination cost. Isn't that the worst of both?",
      "Final: careers compound through relationships. Where do remote relationships — Slack messages, scheduled calls — ever reach that depth?",
    ],
  },
  {
    id: "video-games",
    topic: "Video games are a legitimate competitive sport.",
    skill: "give_a_reason",
    difficulty: "steady",
    turns: 4,
    minutes: 6,
    reminder: "Give one clear reason and defend it.",
    opponentLines: [
      "Chess is accepted as a sport without physical exertion. So 'sport' must mean structured competition — games have that. What's missing?",
      "Esports players train eight hours a day, face burnout, retire at 25. If that's not athletic discipline, what do we call it?",
      "You say reflexes count — pilots have reflexes too. Where's the line that separates sport from skilled performance?",
      "One last challenge: if esports are sports, should the state fund them like sports? Would you accept that consequence?",
    ],
  },
  {
    id: "space-money",
    topic: "Space exploration spending should go to problems on Earth.",
    skill: "concession",
    difficulty: "steady",
    turns: 4,
    minutes: 6,
    reminder: "Concede a point, then hold your ground.",
    opponentLines: [
      "We spend on space what we spend on snacks. The money wouldn't actually reach hospitals. Isn't your argument accounting fiction?",
      "Satellites monitor climate, predict hurricanes, connect the planet. Cutting space spending cuts Earth's tools. How do you answer that?",
      "Every generation says 'fix here first' — and 'here first' never ends. By that logic we'd never have left the savanna. Fair?",
      "Final push: inspiration has measurable returns — enrollment in science careers spikes after missions. Do intangible benefits count in your budget?",
    ],
  },
  {
    id: "phone-ban",
    topic: "Schools should ban phones entirely during the day.",
    skill: "cross_examination",
    difficulty: "sharp",
    turns: 5,
    minutes: 8,
    reminder: "Press their weakest point with a direct question.",
    opponentLines: [
      "Phones are how parents reach kids in an emergency. A total ban means a locked door between a mother and her child. How do you answer that?",
      "Bans just move phone use underground. Kids hide devices; teachers police pockets instead of teaching. Does prohibition ever work?",
      "Some students need phones for medical monitoring or translation. Your policy treats exceptions as threats. Why the blunt instrument?",
      "Attention research shows harm comes from notifications, not possession. Isn't the actual fix 'phones away during class', which most schools already have?",
      "Last question: after the bell, phones help students plan, work, and connect. Are you prepared to defend taking that away from a 17-year-old?",
    ],
  },
  {
    id: "influence-celebrity",
    topic: "Influencers should be legally responsible for the products they promote.",
    skill: "cross_examination",
    difficulty: "sharp",
    turns: 5,
    minutes: 8,
    reminder: "Press their weakest point with a direct question.",
    opponentLines: [
      "Influencers receive thousands for one post. With money comes accountability — isn't that just the normal rule of advertising?",
      "They don't test products; they can't. So we'd be punishing ignorance instead of fraud. Is that justice or theater?",
      "An actor in a TV ad isn't liable for the product. Why should a person filming in their kitchen carry more risk than a corporation's spokesperson?",
      "You'll say 'they built the trust'. But trust in the brand came from the company's own claims, didn't it? Isn't your principle misapplied?",
      "Final: the honest influencers would face legal risk they can't manage, and bad ones would hide behind fine print. Who exactly does your law catch?",
    ],
  },
  {
    id: "identity-online",
    topic: "People should be allowed to use any name and identity online.",
    skill: "nuance",
    difficulty: "sharp",
    turns: 5,
    minutes: 8,
    reminder: "Weigh two competing principles against each other.",
    opponentLines: [
      "Anonymity shelters whistleblowers, abuse survivors, and dissidents. Your principle protects the powerful more than the vulnerable. How do you weigh that?",
      "Harassment campaigns run on pseudonyms. Enforced identity would cool the temperature. Is the chill of anonymity worse than the chill of surveillance?",
      "Countries that mandate real names use it to silence critics. Isn't your rule, exported, a censorship tool?",
      "You say platforms can moderate without identity — but moderation without accountability is a treadmill, isn't it? Ban one account, another appears.",
      "Final weighing: privacy on one side, accountability on the other. If you can only fully protect one, which is it — and why?",
    ],
  },
  {
    id: "money-happiness",
    topic: "Money can buy happiness.",
    skill: "take_a_side",
    difficulty: "gentle",
    turns: 3,
    minutes: 5,
    reminder: "Pick a side and commit.",
    opponentLines: [
      "Research says money lifts happiness until basic needs are met — then the curve flattens. Doesn't that put a ceiling on your claim?",
      "Rich people report no more daily joy, only less stress. Is less stress the same as happiness? Careful — that's a different claim.",
      "The happiest countries aren't the richest. What does that comparison do to your argument?",
      "One more turn: if money could buy happiness, why do lottery winners return to baseline within a year?",
    ],
  },
  {
    id: "ai-art",
    topic: "AI-generated images should count as real art.",
    skill: "counterargument",
    difficulty: "sharp",
    turns: 4,
    minutes: 6,
    reminder: "Make a counterargument, not just a defense.",
    opponentLines: [
      "Photography faced the same objection in 1850 — 'not real art, just a machine'. It's now in every museum. Why is AI different?",
      "Art is intention. A model has none; it predicts pixels. Where in your definition does intention live?",
      "Collage artists sample and remix, and we call them artists. A prompt is a selection among billions of images. How is that different?",
      "Final challenge: if a child and a generative model produce the same image, do they deserve the same recognition? Answer carefully.",
    ],
  },
  {
    id: "four-day",
    topic: "The four-day work week should become standard.",
    skill: "rebuttal",
    difficulty: "steady",
    turns: 4,
    minutes: 7,
    reminder: "Respond to their strongest point directly.",
    opponentLines: [
      "Trials show productivity holds or rises. So the 'economy can't afford it' objection is already dead. What's left of your case?",
      "Customer-facing industries — hospitals, retail — can't compress time. Isn't this a privilege for knowledge workers only?",
      "Fewer hours means higher intensity. Isn't four dense days worse for wellbeing than five normal ones?",
      "Last push: if 32 hours is fine, why not 24? Where's your principled stopping point?",
    ],
  },
];

/** First spar topics for onboarding, keyed loosely to interest tags. */
export const firstSparByInterest: Record<string, string> = {
  tech: "social-media",
  relationships: "social-media",
  money: "money-happiness",
  psychology: "money-happiness",
  society: "phone-ban",
  careers: "four-day",
  gaming: "video-games",
  popculture: "ai-art",
  science: "space-money",
  ethics: "identity-online",
  sports: "video-games",
  weird: "cats-dogs",
};

export const mockLearningPath: LearningPath = {
  levelName: "Counterpoint",
  levelNumber: 3,
  nodes: [
    { id: "take_a_side", order: 1, name: "Take a Side", description: "State a position and hold it under pressure.", stars: 3, status: "complete", topicPreview: "Money can buy happiness." },
    { id: "give_a_reason", order: 2, name: "Give a Reason", description: "Back your position with a clear reason.", stars: 2, status: "complete", topicPreview: "School uniforms are a good idea." },
    { id: "back_it_up", order: 3, name: "Back It Up", description: "Support your reason with a concrete example.", stars: 2, status: "complete", topicPreview: "Homework should be abolished." },
    { id: "counterpoint", order: 4, name: "Counterpoint", description: "Build an argument against theirs, not just for yours.", stars: 0, status: "current", topicPreview: "AI will create more jobs than it destroys." },
    { id: "rebuttal", order: 5, name: "Rebuttal", description: "Respond directly to their strongest point.", stars: 0, status: "locked", topicPreview: "College is no longer worth the cost." },
    { id: "concession", order: 6, name: "Concession", description: "Concede part of their argument without dropping yours.", stars: 0, status: "locked", topicPreview: "Remote work is better for careers." },
    { id: "devils_advocate", order: 7, name: "Devil's Advocate", description: "Defend a position you don't personally agree with.", stars: 0, status: "locked" },
    { id: "cross_examination", order: 8, name: "Cross Examination", description: "Press their weakest point with direct questions.", stars: 0, status: "locked" },
    { id: "evidence", order: 9, name: "Evidence", description: "Weigh examples and proof, not just opinions.", stars: 0, status: "locked" },
    { id: "nuance", order: 10, name: "Nuance", description: "Compare competing principles in abstract debate.", stars: 0, status: "locked" },
  ],
};

/** Derives node status from earned stars so progression updates live. */
export function getEffectivePath(starsByNodeId: Record<string, number>): LearningPath {
  const nodes = mockLearningPath.nodes.map((n) => {
    const stars = (starsByNodeId[n.id] ?? n.stars) as 0 | 1 | 2 | 3;
    return { ...n, stars };
  });
  let currentSet = false;
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    const done = n.stars >= 1;
    if (done) n.status = "complete";
    else if (!currentSet) {
      n.status = "current";
      currentSet = true;
    } else n.status = "locked";
  }
  return { ...mockLearningPath, nodes };
}

export const onboardingOptions = {
  goals: [
    "Speak with more confidence",
    "Sound clearer",
    "Think faster in English",
    "Use better vocabulary",
    "Handle disagreements naturally",
    "Prepare for work or school",
    "Become a stronger speaker",
  ],
  comfort: [
    "I usually avoid speaking",
    "I can speak, but I hesitate a lot",
    "I can hold conversations",
    "I'm comfortable but want to sound sharper",
    "I'm already advanced",
  ],
  interests: [
    { id: "tech", label: "Technology & AI", emoji: "🤖" },
    { id: "relationships", label: "Relationships", emoji: "💬" },
    { id: "money", label: "Money", emoji: "💸" },
    { id: "psychology", label: "Psychology", emoji: "🧠" },
    { id: "society", label: "Society", emoji: "🏛️" },
    { id: "careers", label: "School & careers", emoji: "🎯" },
    { id: "gaming", label: "Gaming", emoji: "🎮" },
    { id: "popculture", label: "Pop culture", emoji: "🎬" },
    { id: "science", label: "Science", emoji: "🔭" },
    { id: "ethics", label: "Ethics", emoji: "⚖️" },
    { id: "sports", label: "Sports", emoji: "🏆" },
    { id: "weird", label: "Weird hypotheticals", emoji: "🌀" },
  ],
  intensity: [
    { id: "easygoing", name: "Easygoing", blurb: "Challenge me, but give me room to think." },
    { id: "balanced", name: "Balanced", blurb: "Don't let weak arguments slide." },
    { id: "bring_it_on", name: "Bring it on", blurb: "Push hard. Make me defend everything." },
  ],
} as const;

/** Onboarding placement insight — demo fixture only. */
export const mockPlacementResult = {
  headline: "You came in strong.",
  path: "Counterpoint — Level 3",
  strengths: ["You explain your reasoning clearly", "You keep speaking while forming ideas"],
  focus: "Building faster rebuttals",
  note: "Every debate you finish tunes this further.",
};

/**
 * Demo fixture only — a session where the user LOSES the debate
 * but earns 3 stars, proving outcome ≠ learning progress.
 */
export const mockLostButThreeStars: DebateReview = {
  outcome: "opponent_win",
  topic: "College is no longer worth the cost.",
  skillName: "Rebuttal",
  stars: { stars: 3, completed: true, skillDemonstrated: true, masteryNote: "You addressed the counterargument directly and dismantled its core assumption." },
  skillAssessment: { targetSkill: "rebuttal", demonstrated: true, summary: "Every response engaged their actual point before restating yours." },
  argumentFeedback: {
    strength: "You challenged the assumption that higher cost automatically means higher quality.",
    improvement: "Your weakest moment was conceding the salary statistic without re-framing it.",
    insight: "Rebutio's salary data was lifetime averages — median early-career gaps are far smaller. That was your opening.",
  },
  languageFeedback: {
    pronunciation: [
      { sound: "th", heardIn: ["think", "three", "worth"], note: 'Your "th" occasionally becomes closer to a "t".', occurrences: 6, severity: "noticeable", timestampSec: 142 },
      { sound: "v / w", heardIn: ["very", "value"], note: 'A light "w" appears where "v" is expected — small, but it repeats.', occurrences: 3, severity: "minor" },
    ],
    fluency: { summary: "You stayed fluent under pressure. Pauses grew slightly during your second rebuttal.", trend: "improving", score: 78 },
    grammar: { summary: "Clean throughout. One habitual pattern: articles occasionally dropped before abstract nouns.", examples: ["— college is investment → a college is an investment"] },
    vocabulary: { summary: "Strong debate vocabulary: 'assumption', 'on balance', 'trade-off'. One more contrast phrase would add range.", examples: ["on balance", "the flip side", "granted, however"] },
    clarity: { summary: "Your examples made the argument easy to follow.", score: 84 },
  },
  xpEarned: 140,
  streakExtended: true,
  nextLevelUnlocked: false,
};

/** Demo fixture only — a drawn debate. */
export const mockDrawReview: DebateReview = {
  ...mockLostButThreeStars,
  outcome: "draw",
  topic: "AI will create more jobs than it destroys.",
  skillName: "Counterargument",
  stars: { stars: 2, completed: true, skillDemonstrated: true, masteryNote: "You built real counterarguments, though one leaned on repetition." },
  argumentFeedback: { strength: "You stayed clear even while answering a counterargument.", improvement: "Your pauses became longer when forming rebuttals.", insight: "You won the analogy battle; Rebutio won on mechanism. A draw was fair." },
  xpEarned: 110,
};

/** Progress stats — demo fixture only. */
export const mockProgressStats: ProgressStats = {
  xp: 2460,
  streakDays: 12,
  streakHistory: [1, 1, 1, 0, 1, 1, 1],
  debatesCompleted: 22,
  wins: 12,
  losses: 7,
  draws: 3,
  skillMastery: [
    { skill: "Rebuttal", level: "Strong" },
    { skill: "Fluency", level: "Improving" },
    { skill: "Pronunciation", level: "Developing" },
  ],
  pronunciationTrend: '"th" pattern is appearing less often than two weeks ago.',
  fluencyTrend: "Longest pause per debate is shrinking — 2.1s average this week.",
};

export const defaultPreferences: OnboardingPreferences = {
  goals: [],
  comfort: "",
  interests: [],
  intensity: "balanced",
};
