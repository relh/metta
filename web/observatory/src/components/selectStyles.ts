import { GroupBase, StylesConfig } from 'react-select'

export type SelectSize = 'sm' | 'md' | 'lg'

const sizeMap: Record<SelectSize, { minHeight: string; fontSize: string; padding: string; valuePadding: string }> = {
  sm: { minHeight: '32px', fontSize: '0.75rem', padding: '6px 10px', valuePadding: '0 6px' },
  md: { minHeight: '36px', fontSize: '0.875rem', padding: '6px 12px', valuePadding: '0 8px' },
  lg: { minHeight: '40px', fontSize: '1rem', padding: '8px 12px', valuePadding: '0 8px' },
}

export function getBaseStyles<O, M extends boolean, G extends GroupBase<O>>(size: SelectSize): StylesConfig<O, M, G> {
  const s = sizeMap[size]
  const bold = size === 'lg'
  return {
    control: (base) => ({
      ...base,
      minHeight: s.minHeight,
      fontSize: s.fontSize,
      ...(bold && { fontWeight: 600, minWidth: '200px' }),
    }),
    valueContainer: (base) => ({ ...base, padding: s.valuePadding }),
    singleValue: (base) => ({
      ...base,
      fontSize: s.fontSize,
      ...(bold && { fontWeight: 600 }),
    }),
    option: (base) => ({ ...base, fontSize: s.fontSize, padding: s.padding }),
    placeholder: (base) => ({ ...base, fontSize: s.fontSize }),
    menu: (base) => ({ ...base, zIndex: 50 }),
    multiValue: (base) => ({ ...base, backgroundColor: '#dbeafe' }),
    multiValueLabel: (base) => ({
      ...base,
      color: '#1e40af',
      fontSize: s.fontSize,
      padding: '1px 4px',
    }),
    multiValueRemove: (base) => ({
      ...base,
      color: '#1e40af',
      ':hover': { backgroundColor: '#bfdbfe', color: '#1e3a8a' },
    }),
  }
}

export function mergeStyles<O, M extends boolean, G extends GroupBase<O>>(
  base: StylesConfig<O, M, G>,
  overrides?: StylesConfig<O, M, G>
): StylesConfig<O, M, G> {
  if (!overrides) return base
  const merged = { ...base } as Record<string, unknown>
  for (const key of Object.keys(overrides)) {
    const baseFn = (base as Record<string, unknown>)[key]
    const overFn = (overrides as Record<string, unknown>)[key]
    if (typeof baseFn === 'function' && typeof overFn === 'function') {
      merged[key] = (provided: unknown, state: unknown) =>
        (overFn as (p: unknown, s: unknown) => unknown)(
          (baseFn as (p: unknown, s: unknown) => unknown)(provided, state),
          state
        )
    } else {
      merged[key] = overFn
    }
  }
  return merged as StylesConfig<O, M, G>
}
