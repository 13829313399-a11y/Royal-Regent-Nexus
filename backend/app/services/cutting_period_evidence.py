"""Month-specific validation projection, separate from full retained audit snapshots."""


def relevant_order(report):
    return bool(report['materials'] or report['production_documents'] or report['usage_documents']
                or any(row['day'] <= report['through'] for row in report['warehouse_documents'])
                or any(row['planned'] or row['missing_days'] for row in report['production']))


def fingerprint_basis(basis):
    reports = []
    for report in basis['orders']:
        # Global revisions and later movements are retained for traceability only.
        # A correction of an old original still changes its effective/reversed state
        # or retained original-document history and therefore invalidates this basis.
        reports.append({key: report[key] for key in (
            'line_id', 'order_snapshot', 'plan_stale', 'production', 'materials', 'issues',
            'production_documents', 'usage_documents')})
        # A newly added task scheduled entirely after this month is not monthly
        # production evidence. Historical/draft documents still keep their task.
        task_ids = {doc['history'][0]['data']['entry']['task_id'] for doc in report['production_documents']}
        reports[-1]['production'] = [row for row in report['production'] if row['task_id'] in task_ids
                                    or row['planned'] or row['missing_days']]
        reports[-1]['warehouse_documents'] = [row for row in report['warehouse_documents']
                                               if row['day'] <= basis['end']]
    return dict(contract='cutting-month-evidence-v2', month=basis['month'],
                previous_lock_id=basis['previous_lock_id'], rows=basis['rows'], orders=reports,
                blockers=basis['blockers'], notices=basis['notices'])
