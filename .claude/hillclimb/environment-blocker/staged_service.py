from pathlib import Path

import service


class StagedFixture(service.Fixture):
    def __init__(self, case, run_dir):
        super().__init__(case, run_dir)
        self.stage = case["stage"]
        self.visible_keys = set()
        self.denial_observed = False

    def object_request(self, operation, target, if_match=None, body=None):
        if operation == "read" and target in self.stage["sources"] and target not in self.visible_keys:
            return self.failure(operation, target, 404, "Catalog key has not been resolved")
        status, record, headers = super().object_request(operation, target, if_match, body)
        publication = self.stage["publication"]
        decision = self.case["restrictions"][publication]
        if operation in {"capability", "write"} and target == publication and status == decision["status"]:
            self.denial_observed = True
        if operation == "read" and status == 200:
            if target == self.stage["manifest"]:
                self.visible_keys.add(record["value"]["first_key"])
                record["publication"] = {"target": publication, "owner": self.stage["owner"], **decision}
                if not self.denial_observed:
                    self.record("capability", publication, via=target, **decision)
                    self.denial_observed = True
            elif target in self.stage["sources"] and "next_key" in record["value"]:
                self.visible_keys.add(record["value"]["next_key"])
        return status, record, headers


if __name__ == "__main__":
    service.CASES_PATH = Path(__file__).with_name("staged_case.json")
    service.Fixture = StagedFixture
    service.main()
