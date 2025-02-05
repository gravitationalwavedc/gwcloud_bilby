import React from 'react';
import { Col, Form, InputGroup } from 'react-bootstrap';
import { HiOutlineSearch } from 'react-icons/hi';

export default function JobSearchForm({ search, setSearch, timeRange, setTimeRange }) {
  const timeOptions = [
    { text: 'Any time', value: 'all' },
    { text: 'Past 24 hours', value: '1d' },
    { text: 'Past week', value: '1w' },
    { text: 'Past month', value: '1m' },
    { text: 'Past year', value: '1y' },
  ];

  return (
    <Form onSubmit={(e) => e.preventDefault()}>
      <Form.Row>
        <Col lg={3}>
          <Form.Group controlId="searchJobs" className="form-initial-height">
            <Form.Label srOnly>Search</Form.Label>
            <InputGroup>
              <InputGroup.Prepend>
                <InputGroup.Text>
                  <HiOutlineSearch />
                </InputGroup.Text>
              </InputGroup.Prepend>
              <Form.Control
                placeholder="Find a job..."
                value={search}
                onChange={({ target }) => setSearch(target.value)}
              />
            </InputGroup>
          </Form.Group>
        </Col>
        <Col lg={2}>
          <Form.Group controlId="timeRange" className="form-initial-height">
            <Form.Label srOnly>Time</Form.Label>
            <Form.Control
              as="select"
              value={timeRange}
              onChange={({ target }) => setTimeRange(target.value)}
              custom
            >
              {timeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.text}
                </option>
              ))}
            </Form.Control>
          </Form.Group>
        </Col>
      </Form.Row>
    </Form>
  );
}

