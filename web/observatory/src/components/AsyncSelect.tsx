import { GroupBase } from 'react-select'
import type { AsyncProps } from 'react-select/async'
import ReactAsyncSelect from 'react-select/async'

import { getBaseStyles, mergeStyles, SelectSize } from './selectStyles'

type AsyncSelectProps<
  Option = unknown,
  IsMulti extends boolean = false,
  Group extends GroupBase<Option> = GroupBase<Option>,
> = AsyncProps<Option, IsMulti, Group> & { size?: SelectSize }

export function AsyncSelect<
  Option = unknown,
  IsMulti extends boolean = false,
  Group extends GroupBase<Option> = GroupBase<Option>,
>({ size = 'sm', styles, ...props }: AsyncSelectProps<Option, IsMulti, Group>) {
  return <ReactAsyncSelect<Option, IsMulti, Group> styles={mergeStyles(getBaseStyles(size), styles)} {...props} />
}
