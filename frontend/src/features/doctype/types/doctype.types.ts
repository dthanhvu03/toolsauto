export type FieldType = "data" | "text" | "int" | "float" | "check" | "select" | "date" | "datetime" | "link" | "table" | "json";

export type DocField = {
  fieldname: string;
  label: string;
  fieldtype: FieldType;
  /** select: danh sách lựa chọn; link / table: tên DocType đích */
  options?: string[] | string;
  required?: boolean;
  unique?: boolean;
  in_list_view?: boolean;
  read_only?: boolean;
  default?: unknown;
  description?: string;
};

export type DocTypeDef = {
  name: string;
  label: string;
  module: string | null;
  description: string | null;
  fields: DocField[];
  is_child: boolean;
  title_field: string | null;
  naming: string;
  modified_at?: number;
  records?: number;
};

export type DocRecordRow = {
  name: string;
  doctype: string;
  data: Record<string, unknown>;
  title?: string;
  created_at: number;
  modified_at: number;
};
