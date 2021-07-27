import subprocess


class Commands:
    @classmethod
    async def run(self, *commands, kwargs=None, error_kls=None, ignore_errors=False):
        for command in commands:
            result = await self.run_command(
                command, kwargs, error_kls=error_kls, ignore_errors=ignore_errors
            )
            yield (command, result)

    @classmethod
    async def run_all(self, *commands, kwargs=None, error_kls=None, ignore_errors=False):
        results = []
        async for command, result in self.run(
            *commands, error_kls=error_kls, ignore_errors=ignore_errors
        ):
            results.append((command, result))

        return results

    @classmethod
    async def run_command(self, command, kwargs=None, error_kls=None, ignore_errors=False):
        try:
            return subprocess.check_output(
                command, **{"stderr": subprocess.PIPE, **(kwargs or {})}
            ).decode(errors="ignore")
        except subprocess.CalledProcessError as error:
            if ignore_errors:
                return

            if error_kls is None:
                raise

            stde = ""
            if error.stderr:
                stde = error.stderr.decode(errors="ignore")

            stdo = ""
            if error.stdout:
                stdo = error.stdout.decode(errors="ignore")

            raise error_kls(error, stde, stdo)
