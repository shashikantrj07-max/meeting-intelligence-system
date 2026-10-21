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
  | "completed"
  | "failed";

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
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
