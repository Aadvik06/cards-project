-- PreciseHub audit data is accessed exclusively by the server through DATABASE_URL.
-- Do not create anon or authenticated policies for these tables: public PostgREST
-- access must remain blocked.
ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommendation_options ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transaction_invoices ENABLE ROW LEVEL SECURITY;
