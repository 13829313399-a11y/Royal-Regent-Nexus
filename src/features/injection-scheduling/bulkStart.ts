export type StartSelection = { machine_id: string; run_id: string };
export type StartReviewRow = StartSelection & {
  machine_code: string;
  mold_code: string;
  order_no: string;
  remaining_shots: number | null;
  can_start: boolean;
  reason: string;
  review_token: string;
  success?: boolean;
};
export type StartReview = {
  revision: number;
  items: StartReviewRow[];
  eligible_count: number;
};
