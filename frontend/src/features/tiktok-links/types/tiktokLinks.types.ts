export type TiktokLinkRow = {
  account_name: string;
  target_page?: string | null;
  target_name?: string | null;
  url: string;
};

export type TiktokLinksResponse = {
  items: TiktokLinkRow[];
  total: number;
  q?: string;
};
