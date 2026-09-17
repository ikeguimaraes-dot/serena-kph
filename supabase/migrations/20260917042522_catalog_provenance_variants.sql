-- Additive: existing manual items and consumers keep their original columns.
ALTER TABLE public.menu_items
  ADD COLUMN IF NOT EXISTS catalog_source text,
  ADD COLUMN IF NOT EXISTS source_item_id text,
  ADD COLUMN IF NOT EXISTS catalog_metadata jsonb,
  ADD COLUMN IF NOT EXISTS source_captured_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS menu_items_source_identity
  ON public.menu_items(restaurant_id, catalog_source, source_item_id)
  WHERE source_item_id IS NOT NULL;
COMMENT ON COLUMN public.menu_items.catalog_metadata IS
  'Source-verified prices, variants and provenance; publication is not evidence of stock or human review.';
