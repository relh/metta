import { Card } from '../../components/Card'
import { TasksTable } from '../../EvalTasks/TasksTable'

export default function EvalTasks() {
  return (
    <div className="p-5 max-w-[1400px] mx-auto">
      <Card title="Remote Jobs">
        <TasksTable />
      </Card>
    </div>
  )
}
