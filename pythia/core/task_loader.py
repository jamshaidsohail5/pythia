import importlib
import os
import yaml

from torch.utils.data import DataLoader

from pythia.utils.meter import Meter
from pythia.core.constants import task_name_mapping


class TaskLoader:
    def __init__(self, config):
        self.config = config
        return

    def load_dataset(self):
        base_task_path = "pythia.tasks"
        self.task_name = self.config['task']

        if self.task_name not in task_name_mapping:
            print("[Error] %s not present in our mapping"
                  % self.task_name)
            return

        task_keyword = task_name_mapping[self.task_name]
        tasks_module = importlib.import_module(base_task_path)
        task_class = getattr(tasks_module, task_keyword)

        self.train_dataset = task_class('train')
        self.dev_dataset = task_class('dev')
        self.test_dataset = task_class('test')

        self.train_dataset.load(**self.config['task_attributes'])
        self.dev_dataset.load(**self.config['task_attributes'])
        self.test_dataset.load(**self.config['task_attributes'])

        self.make_meters()

    def load_config(self):
        directory = os.path.dirname(os.path.abspath(__file__))

        config_path = os.path.join(directory, '..', 'tasks',
                                   self.config['task'], 'config.yml')

        if not os.path.exists(config_path):
            print("[Warning] No config present for task %s" %
                  self.config['task'])
            return

        self.task_config = {}
        with open(config_path, 'r') as f:
            try:
                self.task_config = yaml.load(f)
            except yaml.YAMLError as err:
                print("[Error] Task %s's config yaml error" % self.task_name,
                      err)

    def make_dataloaders(self):
        task_attributes = self.config['task_attributes']
        batch_size = task_attributes['batch_size']
        num_workers = task_attributes['num_workers']

        self.train_loader = DataLoader(dataset=self.train_dataset,
                                       batch_size=batch_size,
                                       shuffle=True,
                                       num_workers=num_workers)
        self.train_loader.dataset_type = 'train'

        self.dev_loader = DataLoader(dataset=self.dev_dataset,
                                     batch_size=batch_size,
                                     shuffle=True,
                                     num_workers=num_workers)
        self.dev_loader.dataset_type = 'dev'

        self.test_loader = DataLoader(dataset=self.test_dataset,
                                      batch_size=batch_size,
                                      shuffle=True,
                                      num_workers=num_workers)
        self.test_loader.dataset_type = 'test'

        self.use_cuda = self.config['use_cuda']

    def make_meters(self):
        task_metrics = self.config['task_attributes']['metrics']
        task_metrics = task_metrics.split(',')

        self.train_meter = Meter('train', self.config, task_metrics)
        self.dev_meter = Meter('dev', self.config, task_metrics)
        self.test_meter = Meter('test', self.config, task_metrics)

    def update_config_for_model(self, config):
        self.train_dataset.update_config_for_model(config)
        self.dev_dataset.update_config_for_model(config)
        self.test_dataset.update_config_for_model(config)

    def report_metrics(self, writer, meter, loss,
                       iteration, should_print=True):
        if not self.config['should_log']:
            return

        dataset_type = meter.get_dataset_type()

        if should_print:
            log_string = meter.get_log_string(loss)
            writer.write(log_string)

        scalars = {}
        for i in range(len(meter.meter_types)):
            meter_type = meter.meter_types[i]
            value = meter.avg_meter_values[i]
            value /= meter.iteration_count

            key = "%s_%s" % (dataset_type, meter_type)
            scalars[key] = value
        writer.add_scalars(scalars, iteration)

    def prepare_batch(self, dataset_type, batch):
        mapping = {
            'train': self.train_dataset,
            'dev': self.dev_dataset,
            'test': self.test_dataset
        }

        return mapping[dataset_type].prepare_batch(batch, self.use_cuda)
