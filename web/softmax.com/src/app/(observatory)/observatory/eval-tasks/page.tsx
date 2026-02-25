import { Card } from "@observatory/components/Card";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";
import { TasksTable } from "@observatory/EvalTasks/TasksTable";

export default function EvalTasks() {
  return (
    <SoftmaxGuard>
      <div className="mx-auto max-w-[1400px] p-5">
        <Card title="Remote Jobs">
          <TasksTable />
        </Card>
      </div>
    </SoftmaxGuard>
  );
}
