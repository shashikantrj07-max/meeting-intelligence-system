export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type MeetingStatus = "draft" | "processing" | "completed" | "failed";
export type MeetingProcessingStage =
  | "pending"
  | "transcribing"
  | "analyzing"
  | "retrying"
  | "completed"
  | "failed";
export type MeetingActionItemStatus = "open" | "in_progress" | "completed";
export type MeetingActionItemHistoryField =
  | "status"
  | "owner"
  | "due_date"
  | "priority";
export type MeetingActionItemAccountabilitySignal =
  | "reopened"
  | "repeated_updates"
  | "stale"
  | "recent_activity";

type Relationship = {
  foreignKeyName: string;
  columns: string[];
  isOneToOne: boolean;
  referencedRelation: string;
  referencedColumns: string[];
};

type Table<Row, Insert, Update, Relationships extends Relationship[] = []> = {
  Row: Row;
  Insert: Insert;
  Update: Update;
  Relationships: Relationships;
};

export type Database = {
  public: {
    Tables: {
      profiles: Table<
        {
          id: string;
          display_name: string | null;
          avatar_url: string | null;
          created_at: string;
          updated_at: string;
        },
        {
          id: string;
          display_name?: string | null;
          avatar_url?: string | null;
          created_at?: string;
          updated_at?: string;
        },
        {
          id?: string;
          display_name?: string | null;
          avatar_url?: string | null;
          created_at?: string;
          updated_at?: string;
        }
      >;
      meetings: Table<
        {
          id: string;
          owner_id: string;
          title: string;
          description: string | null;
          status: MeetingStatus;
          meeting_date: string | null;
          duration_seconds: number | null;
          created_at: string;
          updated_at: string;
        },
        {
          id?: string;
          owner_id: string;
          title: string;
          description?: string | null;
          status?: MeetingStatus;
          meeting_date?: string | null;
          duration_seconds?: number | null;
          created_at?: string;
          updated_at?: string;
        },
        {
          id?: string;
          owner_id?: string;
          title?: string;
          description?: string | null;
          status?: MeetingStatus;
          meeting_date?: string | null;
          duration_seconds?: number | null;
          created_at?: string;
          updated_at?: string;
        },
        [
          {
            foreignKeyName: "meetings_owner_id_fkey";
            columns: ["owner_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_participants: Table<
        {
          id: string;
          meeting_id: string;
          name: string;
          email: string | null;
          role: string | null;
          created_at: string;
        },
        {
          id?: string;
          meeting_id: string;
          name: string;
          email?: string | null;
          role?: string | null;
          created_at?: string;
        },
        {
          id?: string;
          meeting_id?: string;
          name?: string;
          email?: string | null;
          role?: string | null;
          created_at?: string;
        },
        [
          {
            foreignKeyName: "meeting_participants_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: false;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_files: Table<
        {
          id: string;
          meeting_id: string;
          storage_path: string;
          original_filename: string;
          mime_type: string | null;
          file_size_bytes: number | null;
          created_at: string;
        },
        {
          id?: string;
          meeting_id: string;
          storage_path: string;
          original_filename: string;
          mime_type?: string | null;
          file_size_bytes?: number | null;
          created_at?: string;
        },
        {
          id?: string;
          meeting_id?: string;
          storage_path?: string;
          original_filename?: string;
          mime_type?: string | null;
          file_size_bytes?: number | null;
          created_at?: string;
        },
        [
          {
            foreignKeyName: "meeting_files_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: false;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_processing: Table<
        {
          id: string;
          meeting_id: string;
          stage: MeetingProcessingStage;
          error_message: string | null;
          started_at: string | null;
          completed_at: string | null;
          created_at: string;
          updated_at: string;
        },
        {
          id?: string;
          meeting_id: string;
          stage?: MeetingProcessingStage;
          error_message?: string | null;
          started_at?: string | null;
          completed_at?: string | null;
          created_at?: string;
          updated_at?: string;
        },
        {
          id?: string;
          meeting_id?: string;
          stage?: MeetingProcessingStage;
          error_message?: string | null;
          started_at?: string | null;
          completed_at?: string | null;
          created_at?: string;
          updated_at?: string;
        },
        [
          {
            foreignKeyName: "meeting_processing_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: true;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_transcripts: Table<
        {
          id: string;
          meeting_id: string;
          content: string;
          created_at: string;
          updated_at: string;
        },
        {
          id?: string;
          meeting_id: string;
          content: string;
          created_at?: string;
          updated_at?: string;
        },
        {
          id?: string;
          meeting_id?: string;
          content?: string;
          created_at?: string;
          updated_at?: string;
        },
        [
          {
            foreignKeyName: "meeting_transcripts_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: true;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_insights: Table<
        {
          id: string;
          meeting_id: string;
          summary: string;
          key_decisions: Json;
          action_items: Json;
          risks_blockers: Json;
          discussion_points: Json;
          open_questions: Json;
          next_steps: Json;
          created_at: string;
          updated_at: string;
        },
        {
          id?: string;
          meeting_id: string;
          summary: string;
          key_decisions?: Json;
          action_items?: Json;
          risks_blockers?: Json;
          discussion_points?: Json;
          open_questions?: Json;
          next_steps?: Json;
          created_at?: string;
          updated_at?: string;
        },
        {
          id?: string;
          meeting_id?: string;
          summary?: string;
          key_decisions?: Json;
          action_items?: Json;
          risks_blockers?: Json;
          discussion_points?: Json;
          open_questions?: Json;
          next_steps?: Json;
          created_at?: string;
          updated_at?: string;
        },
        [
          {
            foreignKeyName: "meeting_insights_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: true;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_action_items: Table<
        {
          id: string;
          meeting_id: string;
          identity_key: string;
          text: string;
          owner: string | null;
          due_date: string | null;
          priority: string | null;
          evidence: string | null;
          status: MeetingActionItemStatus;
          created_at: string;
          updated_at: string;
        },
        {
          id?: string;
          meeting_id: string;
          identity_key: string;
          text: string;
          owner?: string | null;
          due_date?: string | null;
          priority?: string | null;
          evidence?: string | null;
          status?: MeetingActionItemStatus;
          created_at?: string;
          updated_at?: string;
        },
        {
          id?: string;
          meeting_id?: string;
          identity_key?: string;
          text?: string;
          owner?: string | null;
          due_date?: string | null;
          priority?: string | null;
          evidence?: string | null;
          status?: MeetingActionItemStatus;
          created_at?: string;
          updated_at?: string;
        },
        [
          {
            foreignKeyName: "meeting_action_items_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: false;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_action_item_history: Table<
        {
          id: string;
          action_item_id: string;
          meeting_id: string;
          action_item_text: string;
          field_changed: MeetingActionItemHistoryField;
          previous_value: string | null;
          new_value: string | null;
          changed_at: string;
        },
        never,
        never,
        [
          {
            foreignKeyName: "meeting_action_item_history_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: false;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
      meeting_action_item_signal_reviews: Table<
        {
          action_item_id: string;
          meeting_id: string;
          reviewed_through: string;
          reviewed_at: string;
        },
        never,
        never,
        [
          {
            foreignKeyName: "meeting_action_item_signal_reviews_action_item_id_fkey";
            columns: ["action_item_id"];
            isOneToOne: true;
            referencedRelation: "meeting_action_items";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "meeting_action_item_signal_reviews_meeting_id_fkey";
            columns: ["meeting_id"];
            isOneToOne: false;
            referencedRelation: "meetings";
            referencedColumns: ["id"];
          },
        ]
      >;
    };
    Views: Record<string, never>;
    Functions: {
      enqueue_meeting_processing_job: {
        Args: {
          p_meeting_id: string;
          p_job_type: string;
          p_file_id: string | null;
          p_idempotency_key: string;
        };
        Returns: {
          job_id: string;
          job_status: string;
        }[];
      };
      search_my_meetings: {
        Args: {
          p_query: string;
          p_status?: string;
          p_limit?: number;
        };
        Returns: {
          meeting_id: string;
          title: string;
          description: string | null;
          status: MeetingStatus;
          meeting_date: string | null;
          created_at: string;
          updated_at: string;
          has_transcript: boolean;
          has_intelligence: boolean;
          processing_stage: MeetingProcessingStage | null;
          last_updated: string;
          search_context: string | null;
          matched_in: "title" | "transcript" | "title_and_transcript";
        }[];
      };
    };
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
