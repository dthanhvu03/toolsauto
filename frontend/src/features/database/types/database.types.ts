export type DbTableRow = { name: string; count: number };

export type DatabaseResponse = {
  tables: DbTableRow[];
  total: number;
};
