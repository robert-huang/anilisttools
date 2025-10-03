import math
import random # TODO: replace
from collections import deque


def queue_merge_sort(q):
    # print(q)
    if len(q) > 1:
        return queue_merge_sort(q[2:] + [__merge(q[0], q[1])])
    else:
        return q


def __merge(q1, q2):
    global CURRENT_PROGRESS
    res = deque()
    # print(f'--- subsort start: merging {list(q1)} and {list(q2)} ---')
    while len(q1) + len(q2) > 0:
        if len(q1) == 0:
            res.extend(q2)
            break
        elif len(q2) == 0:
            res.extend(q1)
            break
        left = q1[0]
        right = q2[0]
        choice = picker(left, right)
        # print(f'inserting {q1[0] if choice else q2[0]}')
        if choice:
            res.append(q1.popleft())
        else:
            res.append(q2.popleft())
        CURRENT_PROGRESS += 1
    CURRENT_PROGRESS += len(q1)+len(q2)-1
    # print(f'--- subsort done: {list(res)} ---\n')
    return res


# TODO: replace
# the thing where you get user input to determine the ranking
def picker(a, b):
    res = [True, False]
    random.shuffle(res)
    return res[0]


def main():
    global CURRENT_PROGRESS
    CURRENT_PROGRESS = 0

    ls = list(range(994)) # TODO: replace
    random.shuffle(ls) # TODO: replace
    n = len(ls)
    worst_case_comparisons = round(n*math.log2(n)-n+1)
    print(f'worst_case_comparisons: {worst_case_comparisons}')
    init_queue = [deque([i]) for i in ls]
    queue_merge_sort(init_queue)
    print(CURRENT_PROGRESS)


if __name__ == '__main__':
    main()
