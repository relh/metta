import "dotenv/config";
import { defineConfig } from "prisma/config";

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
  },
  datasource: {
    // Use process.env directly so prisma generate works without a DATABASE_URL
    // (the URL is only needed for migrate/push, not generate)
    url: process.env.DATABASE_URL ?? "",
  },
});
