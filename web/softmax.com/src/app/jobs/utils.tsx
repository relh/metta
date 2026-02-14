import "server-only";

import { MDXComponents } from "mdx/types";
import z from "zod";

import {
  getMdxCollection,
  getMdxDocument,
  MdxDocument,
} from "@/lib/mdxCollection";

const jobSchema = z.object({
  name: z.string(),
  order: z.number(),
});

export type Job = MdxDocument<typeof jobSchema>;

const dir = "src/app/jobs/jobs";

const AboutSoftmax = () => (
  <>
    <h3 className="text-[1.17em] font-bold">
      <strong>About Softmax</strong>
    </h3>
    <p className="my-4">
      We are pioneering the future of AI alignment by building cutting-edge,
      scalable multiplayer environments where AI agents learn the fundamental
      skills of cooperation and competition. Our exceptional team brings
      together deep technical expertise and a powerful vision: to dramatically
      accelerate the success of top-tier ML researchers. Backed by world-class
      investors, we are assembling a cohort of driven individuals who want to do
      the most challenging and impactful work of their careers.
    </p>
  </>
);

const jobMdxComponents: MDXComponents = {
  // I'm not sure if this is useful, but Jekyll version used different heading
  // styles for job postings.
  // Maybe this can be standardized later.
  h2: (props) => <h2 className="text-[1.5em] font-bold" {...props} />,
  h3: (props) => <h3 className="text-[1.17em] font-bold" {...props} />,
  p: (props) => <p className="my-4" {...props} />,
  ul: (props) => <ul className="my-4 list-disc pl-10" {...props} />,
  AboutSoftmax,
};

export async function getJobs(): Promise<Job[]> {
  const jobs = await getMdxCollection({
    dir,
    schema: jobSchema,
    components: jobMdxComponents,
  });

  return jobs.sort((a, b) => a.frontmatter.order - b.frontmatter.order);
}

export async function getJob(slug: string): Promise<Job> {
  return await getMdxDocument({
    dir,
    slug,
    schema: jobSchema,
    components: jobMdxComponents,
  });
}
