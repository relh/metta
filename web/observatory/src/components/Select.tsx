import ReactSelect, { GroupBase, Props } from 'react-select'

import { getBaseStyles, mergeStyles, SelectSize } from './selectStyles'

export type { GroupBase, MultiValue, SingleValue } from 'react-select'

type SelectProps<
  Option = unknown,
  IsMulti extends boolean = false,
  Group extends GroupBase<Option> = GroupBase<Option>,
> = Props<Option, IsMulti, Group> & { size?: SelectSize }

export function Select<
  Option = unknown,
  IsMulti extends boolean = false,
  Group extends GroupBase<Option> = GroupBase<Option>,
>({ size = 'sm', styles, ...props }: SelectProps<Option, IsMulti, Group>) {
  return <ReactSelect<Option, IsMulti, Group> styles={mergeStyles(getBaseStyles(size), styles)} {...props} />
}
