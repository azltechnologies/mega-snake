type ThreadType = "issue" | "pull_request";

export interface ThreadContext {
    repository: {
        owner: string
        repo: string
    }
    id: number;
    type: ThreadType;
}
