export function getPolicyColor(index: number): string {
  const hue = (index * 137.508) % 360
  return `hsl(${hue} 70% 45%)`
}
