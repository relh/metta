import { Card } from '@/components/Card'
import { SoftmaxGuard } from '@/components/SoftmaxGuard'
import { TasksTable } from '@/EvalTasks/TasksTable'

export default function EvalTasks() {
  return (
    <SoftmaxGuard>
      <div className="p-5 max-w-[1400px] mx-auto">
        <Card title="Remote Jobs">
          <TasksTable />
        </Card>
      </div>
    </SoftmaxGuard>
  )
}
