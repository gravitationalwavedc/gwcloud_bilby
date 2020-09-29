import React, { useState, useEffect } from "react";
import {createPaginationContainer, graphql} from "react-relay";
import { Button, Container, Col, Form, InputGroup, Row } from "react-bootstrap";
import { HiOutlineSearch } from "react-icons/hi";
import Link from 'found/lib/Link';
import BaseJobList from "./BaseJobList";
import { HiOutlinePlus } from "react-icons/hi";

const RECORDS_PER_PAGE = 10;

const UserJobList = ({data, match, router,relay}) => {
    const [search, setSearch] = useState("");
    const [timeRange, setTimeRange] = useState("1d");
    const [order, setOrder] = useState();
    const [direction, setDirection] = useState("descending");

    useEffect(() => handleSearchChange(), [search, timeRange, direction, order]);

    const handleSearchChange = () => {
        const refetchVariables = {
            count: RECORDS_PER_PAGE,
            search: search,
            timeRange: timeRange,
            orderBy: order,
            direction: direction
        }
        relay.refetchConnection(1, null, refetchVariables)
    }

    const loadMore = () => {
        if (relay.hasMore()) {
            relay.loadMore(RECORDS_PER_PAGE);
        }
    };

    const timeOptions = [
        {text: 'Any time', value: 'all'},
        {text: 'Past 24 hours', value: '1d'},
        {text: 'Past week', value: '1w'},
        {text: 'Past month', value: '1m'},
        {text: 'Past year', value: '1y'},
    ];

    return (
        <Container >
          <h1 className="pt-5 mb-4">
            My Jobs
            <span className="float-right">
            <Link 
              as={Button}
              variant="outline-primary"
              to='/bilby/' 
              exact 
              match={match}
              router={router}
              className="mr-1">
                Switch to public jobs
              </Link>
              <Link as={Button} to='/bilby/job-form/' exact match={match} router={router}>
                <HiOutlinePlus size={18} className="mb-1 mr-1"/>
                Start a new job 
              </Link>
            </span>
            </h1>
          <Form>
            <Form.Row>
              <Col lg={3}>
                <Form.Group controlId="searchJobs">
                  <Form.Label srOnly>
                    Search
                  </Form.Label>
                  <InputGroup>
                    <InputGroup.Prepend>
                      <InputGroup.Text>
                        <HiOutlineSearch />
                      </InputGroup.Text>
                    </InputGroup.Prepend>
                    <Form.Control placeholder="GW190425" value={search} onChange={({target}) => setSearch(target.value)} />
                  </InputGroup>
                </Form.Group>
              </Col>
              <Col lg={3}>
                <Form.Group controlId="timeRange">
                  <Form.Label srOnly>
                    Time
                  </Form.Label>
                  <Form.Control as="select" value={timeRange} onChange={({target}) => setTimeRange(target.value)} custom>
                    {timeOptions.map(option => <option key={option.value} value={option.value}>{option.text}</option>)}
                  </Form.Control>
                </Form.Group>
              </Col>
            </Form.Row>
          </Form>
          <Row>
            <Col>
              <BaseJobList 
                data={data.bilbyJobs} 
                setOrder={setOrder} 
                order={order} 
                setDirection={setDirection} 
                direction={direction}
                match={match}
                router={router}
                hasMore={relay.hasMore()}
                loadMore={loadMore}
              />
            </Col>
          </Row>
        </Container>
    )
}

export default createPaginationContainer(UserJobList,
    {
        data: graphql`
            fragment UserJobList_data on Query {
                bilbyJobs(
                    first: $count,
                    after: $cursor,
                    orderBy: $orderBy
                ) @connection(key: "UserJobList_bilbyJobs") {
                    edges {
                        node {
                            id
                            name
                            description
                            lastUpdated
                            jobStatus {
                                name
                            }
                            labels {
                                name
                            }
                        }
                    }
                  }
            }
        `,
    },
    {
        direction: 'forward',
        query: graphql`
            query UserJobListForwardQuery(
                $count: Int!,
                $cursor: String,
                $orderBy: String
            ) {
              ...UserJobList_data
            }
        `,
        getConnectionFromProps(props) {
            return props.data && props.data.bilbyJobs
        },

        getFragmentVariables(previousVariables, totalCount) {
            return {
                ...previousVariables,
                count: totalCount
            }
        },

        getVariables(props, {count, cursor}, {orderBy}) {
            return {
                count,
                cursor,
                orderBy,
            }
        }
    }
)
