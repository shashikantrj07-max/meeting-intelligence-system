import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDashboardMeetings,
  buildDashboardSearchMeetings,
  DASHBOARD_MEETING_SEARCH_LIMIT,
  filterDashboardMeetings,
  getDashboardSearchMode,
  getProcessingFailureLabel,
  parseDashboardFilters,
  toDashboardTitleSearchPattern,
} from "../src/lib/dashboard-meetings.ts";

const meetings = [
  {
    id: "one",
    title: "Product planning",
    description: null,
    status: "draft",
    meeting_date: "2026-10-24T10:00:00Z",
    created_at: "2026-10-24T10:00:00Z",
    updated_at: "2026-10-24T10:00:00Z",
  },
  {
    id: "two",
    title: "Design review",
    description: null,
    status: "draft",
    meeting_date: null,
    created_at: "2026-10-25T10:00:00Z",
    updated_at: "2026-10-25T10:00:00Z",
  },
  {
    id: "three",
    title: "Retrospective",
    description: null,
    status: "draft",
    meeting_date: null,
    created_at: "2026-10-26T10:00:00Z",
    updated_at: "2026-10-26T10:00:00Z",
  },
];

function withRelations(
  meeting,
  {
    transcript = null,
    intelligence = null,
    processing = null,
  } = {},
) {
  return {
    ...meeting,
    meeting_transcripts: transcript,
    meeting_insights: intelligence,
    meeting_processing: processing,
  };
}

test("parses URL search and supported meeting status filters", () => {
  assert.deepEqual(
    parseDashboardFilters({ q: "  planning ", status: "completed" }),
    { search: "planning", status: "completed" },
  );
  assert.deepEqual(
    parseDashboardFilters({ q: ["ignored"], status: "unknown" }),
    { search: "", status: "all" },
  );
});

test("escapes title-search wildcards as literal text", () => {
  assert.equal(toDashboardTitleSearchPattern(" planning "), "% planning %");
  assert.equal(toDashboardTitleSearchPattern("50%_\\complete"), "%50\\%\\_\\\\complete%");
});

test("distinguishes empty, too-short, and searchable queries", () => {
  assert.equal(getDashboardSearchMode("  "), "all");
  assert.equal(getDashboardSearchMode("ab"), "too_short");
  assert.equal(getDashboardSearchMode("meeting"), "search");
});

test("maps title and transcript search results with bounded result count", () => {
  assert.equal(DASHBOARD_MEETING_SEARCH_LIMIT, 25);
  assert.deepEqual(buildDashboardSearchMeetings([]), []);
  const [meeting] = buildDashboardSearchMeetings([
    {
      meeting_id: "transcript-match",
      title: "Quarterly planning",
      description: null,
      status: "completed",
      meeting_date: null,
      created_at: "2026-10-24T10:00:00Z",
      updated_at: "2026-10-24T10:00:00Z",
      has_transcript: true,
      has_intelligence: true,
      processing_stage: "completed",
      last_updated: "2026-10-25T10:00:00Z",
      search_context: "Discussed [budget] priorities.",
      matched_in: "transcript",
    },
  ]);
  assert.equal(meeting.id, "transcript-match");
  assert.equal(meeting.matchedIn, "transcript");
  assert.equal(meeting.searchContext, "Discussed [budget] priorities.");
  assert.equal(meeting.hasTranscript, true);
});

test("filters meetings by case-insensitive title and processing state", () => {
  const enriched = buildDashboardMeetings(
    meetings.map((meeting, index) =>
      withRelations(meeting, {
        processing: {
          meeting_id: meeting.id,
          stage: ["completed", "analyzing", "failed"][index],
          updated_at: meeting.updated_at,
        },
      }),
    ),
  );

  assert.deepEqual(
    filterDashboardMeetings(enriched, { search: "DESIGN", status: "all" }).map(
      ({ id }) => id,
    ),
    ["two"],
  );
  assert.deepEqual(
    filterDashboardMeetings(enriched, { search: "", status: "processing" }).map(
      ({ id }) => id,
    ),
    ["two"],
  );
  assert.deepEqual(
    filterDashboardMeetings(enriched, { search: "", status: "completed" }).map(
      ({ id }) => id,
    ),
    ["one"],
  );
  assert.deepEqual(
    filterDashboardMeetings(enriched, { search: "", status: "failed" }).map(
      ({ id }) => id,
    ),
    ["three"],
  );
  assert.deepEqual(
    filterDashboardMeetings(enriched, {
      search: "review",
      status: "completed",
    }),
    [],
  );
});

test("enriches meetings with transcript, intelligence, and processing indicators", () => {
  const enriched = buildDashboardMeetings(
    meetings.map((meeting) => {
      if (meeting.id === "one") {
        return withRelations(meeting, {
          transcript: {
            meeting_id: "one",
            updated_at: "2026-10-27T10:00:00Z",
          },
          intelligence: {
            meeting_id: "one",
            updated_at: "2026-10-28T10:00:00Z",
          },
        });
      }
      if (meeting.id === "two") {
        return withRelations(meeting, {
          processing: {
            meeting_id: "two",
            stage: "analyzing",
            updated_at: "2026-10-29T10:00:00Z",
          },
        });
      }
      return withRelations(meeting);
    }),
  );

  assert.equal(enriched[0].hasTranscript, true);
  assert.equal(enriched[0].hasIntelligence, true);
  assert.equal(enriched[0].processingStage, null);
  assert.equal(enriched[0].lastUpdated, "2026-10-28T10:00:00Z");

  assert.equal(enriched[1].hasTranscript, false);
  assert.equal(enriched[1].hasIntelligence, false);
  assert.equal(enriched[1].processingStage, "analyzing");
  assert.equal(enriched[1].lastUpdated, "2026-10-29T10:00:00Z");

  assert.equal(enriched[2].hasTranscript, false);
  assert.equal(enriched[2].hasIntelligence, false);
});

test("normalizes embedded relations returned as arrays", () => {
  const [enriched] = buildDashboardMeetings([
    withRelations(meetings[0], {
      transcript: [{ meeting_id: "one", updated_at: "2026-10-27T10:00:00Z" }],
      intelligence: [
        { meeting_id: "one", updated_at: "2026-10-28T10:00:00Z" },
      ],
      processing: [
        {
          meeting_id: "one",
          stage: "analyzing",
          updated_at: "2026-10-29T10:00:00Z",
        },
      ],
    }),
  ]);

  assert.equal(enriched.hasTranscript, true);
  assert.equal(enriched.hasIntelligence, true);
  assert.equal(enriched.processingStage, "analyzing");
  assert.equal(enriched.lastUpdated, "2026-10-29T10:00:00Z");
});

test("distinguishes transcription failure from intelligence failure", () => {
  assert.equal(getProcessingFailureLabel("failed", false), "Transcription failed");
  assert.equal(getProcessingFailureLabel("failed", true), "Intelligence failed");
  assert.equal(getProcessingFailureLabel("analyzing", true), null);
});
