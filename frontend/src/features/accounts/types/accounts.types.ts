export type AccountsResponse = {
  accounts: {
    id: number;
    name: string;
    platform: string;
    is_active: boolean;
    login_status?: string;
    daily_limit?: number;
    target_page?: string | null;
    consecutive_failures?: number;
  }[];
  total: number;
};

export type AccountRow = AccountsResponse["accounts"][number];
