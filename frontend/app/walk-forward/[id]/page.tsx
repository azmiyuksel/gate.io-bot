import { WalkForwardDetail } from "@/components/walkforward-detail";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WalkForwardDetail id={id} />;
}
